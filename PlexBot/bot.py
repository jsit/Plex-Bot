import logging
from queue import Queue

import discord
from discord import FFmpegPCMAudio
from discord.ext import commands
from discord.ext.commands import command
from fuzzywuzzy import fuzz
from plexapi.exceptions import Unauthorized
from plexapi.server import PlexServer

import datetime
from urllib.request import urlopen

import io

logger = logging.getLogger("PlexBot")


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def kill(self, ctx):
        await ctx.send(f"Stopping upon the request of {ctx.author.mention}")
        await self.bot.close()
        logger.info(f"Stopping upon the request of {ctx.author.mention}")


class Plex(commands.Cog):
    def __init__(self, bot, base_url, plex_token, lib_name) -> None:
        self.bot = bot
        self.base_url = base_url
        self.plex_token = plex_token
        self.library_name = lib_name

        try:
            self.pms = PlexServer(self.base_url, self.plex_token)
        except Unauthorized:
            logger.fatal("Invalid Plex token, stopping...")
            raise Unauthorized("Invalid Plex token")

        self.music = self.pms.library.section(self.library_name)

        self.vc = None
        self.current_track = None
        self.play_queue = Queue()

        logger.info("Started bot successfully")

    def _search_tracks(self, title):
        tracks = self.music.searchTracks()
        score = [None, -1]
        for i in tracks:
            s = fuzz.ratio(title.lower(), i.title.lower())
            if s > score[1]:
                score[0] = i
                score[1] = s
            elif s == score[1]:
                score[0] = i

        return score[0]

    @command()
    async def hello(self, ctx, *, member: discord.member = None):
        member = member or ctx.author
        await ctx.send(f"Hello {member}")

    async def _after_callback(self, error=None):
        logger.debug("After callbacked")
        if self.play_queue.empty():
            self.current_track = None
            logger.debug("No tracks left in queue, returning")
        else:
            track = self.play_queue.get()
            audio_stream = FFmpegPCMAudio(track.getStreamURL())
            self.current_track = track
            logger.debug(f"Started playing next song in queue: {track.title}")
            self.vc.play(audio_stream)
            embed, f = self._build_play_embed(self.current_track)
            await self.callback_ctx.send(embed=embed, file=f)

    def _build_play_embed(self, track):
        """Creates a pretty embed card.



        """

        # Grab the relevant thumbnail
        img_stream = urlopen(track.thumbUrl)
        img = io.BytesIO(img_stream.read())

        # Attach to discord embed
        f = discord.File(img, filename="image0.png")
        descrip = f"{track.album().title} - {track.artist().title}"

        logger.debug(f"URL: {track.thumbUrl}")
        logger.debug(f"Description: {descrip}")

        # Build the actual embed
        embed = discord.Embed(
            title=track.title, description=descrip, colour=discord.Color.red()
        )
        dur_seconds = track.duration
        dur_str = str(datetime.timedelta(seconds=dur_seconds))
        dur_str = f"Duration: {dur_str}"

        embed.set_footer(text=dur_str)
        embed.set_thumbnail(url="attachment://image0.png")
        embed.set_author(name="Plex")

        return embed, f

    @command()
    async def play(self, ctx, *args):
        if not len(args):
            await ctx.send("Usage: play TITLE_OF_SONG")
            return

        title = " ".join(args)
        track = self._search_tracks(title)
        if track:
            track_url = track.getStreamURL()
            if not ctx.author.voice:
                await ctx.send("Join a voice channel first!")
                return
            if not self.vc:
                self.vc = await ctx.author.voice.channel.connect()
                logger.debug("Connected to vc.")

            if self.vc.is_playing():
                self.play_queue.put(track)
                self.callback_ctx = ctx
                await ctx.send(f"Added {track.title} to queue.")
                logger.debug(f"Added {track.title} to queue.")
            else:
                audio_stream = FFmpegPCMAudio(track_url)
                self.vc.play(audio_stream, after=self._after_callback)
                self.current_track = track
                logger.debug(f"Playing {track.title}")
                embed, f = self._build_play_embed(self.current_track)
                await ctx.send(embed=embed, file=f)
        else:
            logger.debug(f"{title} was not found.")
            await ctx.send(f"{title} was not found.")

    @command()
    async def stop(self, ctx):
        if self.vc:
            self.vc.stop()
            await self.vc.disconnect()
            self.vc = None
            await ctx.send("Stopped")

    @command()
    async def pause(self, ctx):
        if self.vc:
            self.vc.pause()
            await ctx.send("Paused")

    @command()
    async def resume(self, ctx):
        if self.vc:
            self.vc.resume()
            await ctx.send("Resumed")

    @command()
    async def skip(self, ctx):
        logger.debug("Skip")
        if self.vc:
            self.vc.stop()
            await self._after_callback()

    @command()
    async def np(self, ctx):
        await ctx.send(f"Currently playing: {self.current_track.title}")

    @command()
    async def queue(self, ctx):
        message = ""
        for i in self.play_queue:
            message += self.play_queue.title + "\n"
        await ctx.send(f"Play Queue: {message}")

    @command()
    async def clear(self, ctx):
        self.play_queue = Queue()
        await ctx.send("Queue cleared.")
