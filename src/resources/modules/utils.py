from os import listdir
from re import compile
from ..structures import Bloxlink, DonatorProfile
from ..exceptions import RobloxAPIError, RobloxDown, RobloxNotFound, Message
from config import PREFIX, HTTP_RETRY_LIMIT # pylint: disable=E0611
from ..constants import RELEASE
from discord.errors import NotFound, Forbidden
from discord.utils import find
from discord import Object
from aiohttp.client_exceptions import ClientOSError, ServerDisconnectedError
from time import time
from math import ceil
import asyncio

is_patron = Bloxlink.get_module("patreon", attrs="is_patron")

@Bloxlink.module
class Utils(Bloxlink.Module):
	def __init__(self):
		self.option_regex = compile("(.+):(.+)")
		self.bloxlink_server = self.client.get_guild(372036754078826496)


	async def __setup__(self):
		try:
			self.bloxlink_server = self.bloxlink_server or self.client.get_guild(372036754078826496) or await self.client.fetch_guild(372036754078826496)
		except Forbidden:
			self.bloxlink_server = None

	@staticmethod
	def get_files(directory):
		return [name for name in listdir(directory) if name[:1] != "." and name[:2] != "__" and name != "_DS_Store"]

	async def fetch(self, url, raise_on_failure=True, retry=HTTP_RETRY_LIMIT):
		try:
			async with self.session.get(url) as response:
				text = await response.text()

				if raise_on_failure:
					if response.status >= 500:
						if retry != 0:
							retry -= 1
							await asyncio.sleep(1.0)

							return await self.fetch(url, raise_on_failure=raise_on_failure, retry=retry)

						raise RobloxAPIError

					elif response.status == 400:
						raise RobloxAPIError
					elif response.status == 404:
						raise RobloxNotFound

				if text == "The service is unavailable.":
					raise RobloxDown

				return text, response

		except ServerDisconnectedError:
			if retry != 0:
				return await self.fetch(url, raise_on_failure=raise_on_failure, retry=retry-1)
			else:
				raise ServerDisconnectedError

		except ClientOSError:
			# TODO: raise HttpError with non-roblox URLs
			raise RobloxAPIError

	async def get_prefix(self, guild=None, guild_data=None, trello_board=None):
		if not guild:
			return PREFIX, None

		if RELEASE == "MAIN" and await guild.fetch_member(469652514501951518):
			return "!!", None

		if trello_board:
			List = await trello_board.get_list(lambda L: L.name == "Bloxlink Settings")

			if List:
				card = await List.get_card(lambda c: c.name[:6] == "prefix")

				if card:
					if card.name == "prefix":
						if card.desc:
							return card.desc.strip(), card

					else:
						match = self.option_regex.search(card.name)

						if match:
							return match.group(2), card



		guild_data = guild_data or await self.r.db("canary").table("guilds").get(str(guild.id)).run() or {}
		prefix = guild_data.get("prefix")

		return prefix or PREFIX, None


	async def validate_guild(self, guild):
		owner = guild.owner

		if not self.bloxlink_server:
			return True

		profile, _ = await self.is_premium(owner)
		if profile.features.get("premium"):
			return True

		try:
			member = self.bloxlink_server.get_member(owner.id) or await self.bloxlink_server.fetch_member(owner.id)
		except NotFound:
			return False

		if member:
			if find(lambda r: r.name == "3.0 Access", member.roles):
				return True


		return False


	async def add_features(self, user, features, *, days=-1, code=None, premium_anywhere=None):
		user_data = await self.r.table("users").get(str(user.id)).run() or {"id": str(user.id)}
		user_data_premium = user_data.get("premium") or {}
		prem_expiry = user_data_premium.get("expiry", 1)

		if days != -1 and days != 0:
			t = time()

			if prem_expiry and prem_expiry > t:
				# premium is still active; add time to it
				days = (days * 86400) + prem_expiry
			else:
				# premium expired
				days = (days * 86400) + t
		elif days == -1:
			days = prem_expiry
		elif days == "-":
			days = 1

		if code:
			# delete_code()
			# add code to redeemed
			pass

		if "pro" in features:
			user_data_premium["pro"] = days # TODO: convert to -1

		if "premium" in features:
			user_data_premium["expiry"] = days # TODO: convert to -1

		if premium_anywhere:
			user_data["flags"] = user_data.get("flags") or {}
			user_data["flags"]["premiumAnywhere"] = True

		if "-" in features:
			if "premium" in features:
				user_data_premium["expiry"] = 1

			if "pro" in features:
				user_data_premium["pro"] = 1

			if len(features) == 1:
				user_data_premium["expiry"] = 1
				user_data_premium["pro"] = 1

		user_data["premium"] = user_data_premium


		await self.r.table("users").insert(user_data, conflict="update").run()


	async def has_selly_premium(self, author, author_data):
		premium = author_data.get("premium") or {}
		expiry = premium.get("expiry", 1)
		pro_expiry = premium.get("pro", 1)

		t = time()
		is_p = expiry == 0 or expiry > t
		days_premium = expiry != 0 and expiry > t and ceil((expiry - t)/86400) or 0

		pro_access = pro_expiry == 0 or pro_expiry > t
		pro_days = pro_expiry != 0 and pro_expiry > t and ceil((pro_expiry - t)/86400) or 0

		return {
			"premium": is_p,
			"days": days_premium,
			"pro_access": pro_access,
			"pro_days": pro_days,
			"codes_redeemed": premium.get("redeemed", {})
		}


	async def has_patreon_premium(self, author, author_data):
		patron_data = await is_patron(author)

		return patron_data


	async def transfer_premium(self, transfer_from, transfer_to):
		profile, _ = await self.is_premium(transfer_to)
		if profile.features.get("premium"):
			raise Message("This user already has premium!", type="silly")

		if transfer_from == transfer_to:
			raise Message("You cannot transfer premium to yourself!")


		transfer_from_data = await self.r.table("users").get(str(transfer_from.id)).run() or {"id": str(transfer_from.id)}
		transfer_to_data   = await self.r.table("users").get(str(transfer_to.id)).run() or {"id": str(transfer_to.id)}

		transfer_from_data["premium"] = transfer_from_data.get("premium", {})
		transfer_to_data["premium"]   = transfer_to_data.get("premium", {})

		transfer_from_data["premium"]["transferTo"] = str(transfer_to.id)
		transfer_to_data["premium"]["transferFrom"] = str(transfer_from.id)

		await self.r.table("users").insert(transfer_from_data, conflict="update").run()
		await self.r.table("users").insert(transfer_to_data,   conflict="update").run()


	async def is_premium(self, author, author_data=None, rec=True):
		profile = DonatorProfile(author)

		author_data = author_data or await self.r.table("users").get(str(author.id)).run() or {"id": str(author.id)}
		premium_data = author_data.get("premium") or {}

		if rec:
			if premium_data.get("transferTo"):
				return profile, premium_data["transferTo"]
			elif premium_data.get("transferFrom"):
				transfer_from = premium_data["transferFrom"]
				transferee_data = await self.r.table("users").get(str(transfer_from)).run() or {}
				transferee_premium, _ = await self.is_premium(Object(id=transfer_from), transferee_data, rec=False)

				if transferee_premium:
					return transferee_premium, _
				else:
					premium_data["transferFrom"] = None
					transferee_data["transferTo"] = None

					author_data["premium"] = premium_data
					transferee_data["premium"] = transferee_data

					await self.r.table("users").insert(author_data, conflict="update").run()
					await self.r.table("users").insert(transferee_data, conflict="update").run()


		if author_data.get("flags", {}).get("premiumAnywhere"):
			profile.attributes["PREMIUM_ANYWHERE"] = True

		data_patreon = await self.has_patreon_premium(author, author_data)

		if data_patreon:
			profile.load_patreon(data_patreon)
			profile.add_features("premium", "pro")
		else:
			data_selly = await self.has_selly_premium(author, author_data)

			if data_selly["premium"]:
				profile.add_features("premium")
				profile.load_selly(days=data_selly["days"])

			if data_selly["pro_access"]:
				profile.add_features("pro")


		return profile, None
