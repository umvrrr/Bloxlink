from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error
from resources.exceptions import PermissionError # pylint: disable=import-error
from discord.errors import NotFound, Forbidden
import time


@Bloxlink.command
class PingCommand(Bloxlink.Module):
    """measure the latency between the bot and Discord"""

    def __init__(self):
        pass

    async def __main__(self, CommandArgs):
        message = CommandArgs.message
        response = CommandArgs.response

        t_1 = time.perf_counter()

        if response.webhook_only:
            m = await response.send("Pinging...")
        else:
            try:
                await message.channel.trigger_typing()
            except NotFound:
                pass

        t_2 = time.perf_counter()
        time_delta = round((t_2-t_1)*1000)

        if response.webhook_only:
            try:
                await m.delete()
            except NotFound:
                pass
            except Forbidden:
                raise PermissionError("Please make sure I have the ``Manage Messages`` "
                                      "permission.")
            else:
                await response.send(f"Pong! ``{time_delta}ms``")
        else:
            await response.send(f"Pong! ``{time_delta}ms``")
