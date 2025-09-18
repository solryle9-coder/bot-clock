import discord
from discord.ext import commands
from discord import app_commands, ButtonStyle
from discord.ui import Button, View
import os
from datetime import datetime
import pytz

# Channel Configuration
BUTTON_CHANNEL_ID = 1418080452639461440  # Channel for Clock In/Out button message and ephemeral responses
UPDATE_REPORTS_CHANNEL_ID = 1418080010484453396  # Channel for status report submissions (update reports)
LOG_CHANNEL_ID = 1418013767341703359    # Private channel for clock-in/out and status report logs
WERT_USER_ID = '1270796696259133501'  # Wert's user ID
CATEGORY_ID = os.getenv('CATEGORY_ID', '1418080302424785026')  # Use env variable or fallback

# Set up the bot with necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Time zone for CDT
CDT = pytz.timezone('America/Chicago')

# Global variable to track clock-in state per user
clocked_in_users = {}

# Global variable to track private status channels per user
user_private_channels = {}

# Persistent view for buttons
class ClockButtons(View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent view (no timeout)

    @discord.ui.button(label="Clock In", style=ButtonStyle.success, custom_id="clock_in_button")
    async def clock_in_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        if user_id not in clocked_in_users:
            clocked_in_users[user_id] = {
                'clocked_in': False,
                'clock_out_enabled': False,
                'clock_in_time': None
            }
        if clocked_in_users[user_id]['clocked_in']:
            await interaction.followup.send("You are already clocked in!", ephemeral=True)
            return
        clocked_in_users[user_id]['clocked_in'] = True
        clocked_in_users[user_id]['clock_out_enabled'] = False
        clock_in_dt = datetime.now(CDT)
        clocked_in_users[user_id]['clock_in_time'] = clock_in_dt
        # Create private status channel for the user
        guild = interaction.guild
        category = guild.get_channel(int(CATEGORY_ID))
        if not category:
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error: Category {CATEGORY_ID} not found for creating private channel for {interaction.user.name} (ID: {user_id})")
            await interaction.followup.send("Error: Category for private channels not found. Please contact an admin.", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_messages=True,
                read_message_history=True,
                use_application_commands=True
            )
        }
        try:
            private_channel = await guild.create_text_channel(
                f"report-001-{str(user_id)[-4:]}",
                overwrites=overwrites,
                category=category
            )
            user_private_channels[user_id] = private_channel.id
            await private_channel.send(
                f"{interaction.user.mention}, please submit your report here. "
                "Make sure your report must start with 'Status Report' (case sensitive) and it must have at least one attachment."
            )
        except Exception as e:
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error creating private channel for {interaction.user.name} (ID: {user_id}) in category {CATEGORY_ID}: {str(e)}")
            await interaction.followup.send("Error creating your private status channel. Please contact an admin.", ephemeral=True)
            return
        # Log clock-in to private channel
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            date_str = clock_in_dt.strftime("%Y-%m-%d")
            time_str = clock_in_dt.strftime("%I:%M:%S %p %Z")
            await log_channel.send(f"<@{user_id}> clocked in ({date_str}) ({time_str})")
        await interaction.followup.send(
            f"You have clocked in! Please submit a Status Report with an attachment in your private status channel: {private_channel.mention}.",
            ephemeral=True
        )

    @discord.ui.button(label="Clock Out", style=ButtonStyle.danger, custom_id="clock_out_button")
    async def clock_out_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        button_channel = bot.get_channel(BUTTON_CHANNEL_ID)
        if not button_channel:
            await interaction.followup.send("Error: Button channel not found!", ephemeral=True)
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error: Button channel {BUTTON_CHANNEL_ID} not found for user {interaction.user.name} (ID: {user_id})")
            return
        if user_id not in clocked_in_users or not clocked_in_users[user_id]['clocked_in']:
            await interaction.followup.send("Please clock in first!", ephemeral=True)
            return
        if not clocked_in_users[user_id]['clock_out_enabled']:
            await interaction.followup.send(
                f"{interaction.user.mention}, please submit a status report in your private status channel.",
                ephemeral=True
            )
            return
        try:
            clock_out_dt = datetime.now(CDT)
            clock_in_dt = clocked_in_users[user_id]['clock_in_time']
            time_diff = clock_out_dt - clock_in_dt
            total_seconds = time_diff.total_seconds()
            total_hours = int(total_seconds // 3600)
            total_minutes = int((total_seconds % 3600) // 60)
            clocked_in_users[user_id] = {
                'clocked_in': False,
                'clock_out_enabled': False,
                'clock_in_time': None
            }
            # Delete private channel if it exists
            if user_id in user_private_channels:
                try:
                    private_channel = bot.get_channel(user_private_channels[user_id])
                    if private_channel:
                        await private_channel.delete()
                        log_channel = bot.get_channel(LOG_CHANNEL_ID)
                        if log_channel:
                            date_str = clock_out_dt.strftime("%Y-%m-%d")
                            time_str = clock_out_dt.strftime("%I:%M:%S %p %Z")
                            await log_channel.send(
                                f"Private channel report-001-{str(user_id)[-4:]} for {interaction.user.name} (ID: {user_id}) "
                                f"in category {CATEGORY_ID} deleted at ({date_str}) ({time_str})"
                            )
                    del user_private_channels[user_id]
                except Exception as e:
                    wert_user = await bot.fetch_user(WERT_USER_ID)
                    if wert_user:
                        await wert_user.send(f"Error deleting private channel for {interaction.user.name} (ID: {user_id}) in category {CATEGORY_ID}: {str(e)}")
            # Log clock-out to private channel
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                date_str = clock_out_dt.strftime("%Y-%m-%d")
                time_str = clock_out_dt.strftime("%I:%M:%S %p %Z")
                await log_channel.send(
                    f"<@{user_id}> clocked out ({date_str}) ({time_str}) ({total_hours} hours) ({total_minutes} minutes)"
                )
            await interaction.followup.send("You have clocked out!", ephemeral=True)
        except Exception as e:
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error in clock_out_button for {interaction.user.name} (ID: {user_id}): {str(e)}")
            await interaction.followup.send("An error occurred while clocking out. Please contact an admin.", ephemeral=True)

# Event: Bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        # Sync commands
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
        # Register persistent view
        bot.add_view(ClockButtons())
        # Send button message to button channel with instructions
        button_channel = bot.get_channel(BUTTON_CHANNEL_ID)
        if button_channel:
            view = ClockButtons()
            instructions = (
                "Use the buttons to clock in or out!\n"
                "**Instructions:**\n"
                "1. Click 'Clock In' to start your session.\n"
                "2. A private status channel (report-001-[suffix]) will be created for you in the designated category.\n"
                "3. Submit a Status Report with an attachment in your private channel (must start with 'Status Report', case sensitive).\n"
                "4. After submitting, your report will be copied to the update reports channel, and your private channel will be deleted.\n"
                "5. Click 'Clock Out' to end your session.\n"
                "6. Use `/checkstate` to check your clock-in status (works in any channel, including your private status channel).\n"
                "7. Use `/reset @user` to clock in any user without needing a status report (one-time bypass).\n"
                "Contact <@1270796696259133501> if you encounter any issues."
            )
            await button_channel.send(instructions, view=view)
            print(f"Sent button message to button channel {BUTTON_CHANNEL_ID}")
        else:
            print(f"Could not find button channel {BUTTON_CHANNEL_ID}")
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error: Could not find button channel {BUTTON_CHANNEL_ID}")
        # Log bot startup
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            clock_dt = datetime.now(CDT)
            date_str = clock_dt.strftime("%Y-%m-%d")
            time_str = clock_dt.strftime("%I:%M:%S %p %Z")
            await log_channel.send(f"Bot {bot.user.name} is online at ({date_str}) ({time_str})")
        else:
            print(f"Could not find log channel {LOG_CHANNEL_ID}")
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error: Could not find log channel {LOG_CHANNEL_ID}")
    except Exception as e:
        print(f"Error in on_ready: {e}")
        wert_user = await bot.fetch_user(WERT_USER_ID)
        if wert_user:
            await wert_user.send(f"Error in on_ready: {str(e)}")

# Event: Check for status report messages
@bot.event
async def on_message(message: discord.Message):
    user_id = message.author.id
    if user_id in user_private_channels and message.channel.id == user_private_channels[user_id]:
        if message.content.startswith("Status Report") and len(message.attachments) >= 1:
            clocked_in_users[user_id]['clock_out_enabled'] = True
            # Remove "Status Report" prefix from content
            report_content = message.content.replace("Status Report", "", 1).strip()
            # Copy report to update reports channel
            update_channel = bot.get_channel(UPDATE_REPORTS_CHANNEL_ID)
            if update_channel:
                try:
                    await update_channel.send(
                        f"Status Report from {message.author.mention}: {report_content}",
                        files=[await att.to_file() for att in message.attachments]
                    )
                except Exception as e:
                    wert_user = await bot.fetch_user(WERT_USER_ID)
                    if wert_user:
                        await wert_user.send(f"Error copying report to update channel for {message.author.name} (ID: {user_id}): {str(e)}")
            # Send confirmation in button channel
            button_channel = bot.get_channel(BUTTON_CHANNEL_ID)
            if button_channel:
                await button_channel.send(
                    f"{message.author.mention} you can now clockout\n> {message.content}\n(Message link: {message.jump_url})"
                )
            # Log status report detection
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                clock_dt = datetime.now(CDT)
                date_str = clock_dt.strftime("%Y-%m-%d")
                time_str = clock_dt.strftime("%I:%M:%S %p %Z")
                await log_channel.send(
                    f"Status Report detected from {message.author.name} (ID: {message.author.id}) "
                    f"at ({date_str}) ({time_str}) with {len(message.attachments)} attachment(s): {message.content}"
                )
            # Delete the private channel
            try:
                await message.channel.delete()
                del user_private_channels[user_id]
                if log_channel:
                    await log_channel.send(
                        f"Private channel report-001-{str(user_id)[-4:]} for {message.author.name} (ID: {user_id}) "
                        f"in category {CATEGORY_ID} deleted at ({date_str}) ({time_str})"
                    )
            except Exception as e:
                wert_user = await bot.fetch_user(WERT_USER_ID)
                if wert_user:
                    await wert_user.send(f"Error deleting private channel for {message.author.name} (ID: {user_id}) in category {CATEGORY_ID}: {str(e)}")
        else:
            # Inform user if report is invalid
            await message.channel.send(
                "Please submit a valid Status Report starting with 'Status Report' (case sensitive) and including at least one attachment."
            )
    await bot.process_commands(message)

# Command: Check clock-in state
@app_commands.command(name="checkstate", description="Check clock-in state")
async def checkstate(interaction: discord.Interaction):
    state = clocked_in_users.get(interaction.user.id, {'clocked_in': False, 'clock_out_enabled': False})
    await interaction.response.send_message(
        f"Clocked in: {state['clocked_in']}, Clock out enabled: {state['clock_out_enabled']}",
        ephemeral=True
    )

# Command: Reset and clock in any user without report requirement
@app_commands.command(name="reset", description="Reset and clock in a user, bypassing status report requirement for this session")
@app_commands.describe(user="The user to reset and clock in (mention or ID)")
async def reset(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    target_user = user
    user_id = target_user.id
    guild = interaction.guild
    # Reset user state
    clocked_in_users[user_id] = {
        'clocked_in': True,
        'clock_out_enabled': True,  # Allow clock out without report
        'clock_in_time': datetime.now(CDT)
    }
    # Delete existing private channel if it exists
    if user_id in user_private_channels:
        try:
            private_channel = bot.get_channel(user_private_channels[user_id])
            if private_channel:
                await private_channel.delete()
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    clock_dt = datetime.now(CDT)
                    date_str = clock_dt.strftime("%Y-%m-%d")
                    time_str = clock_dt.strftime("%I:%M:%S %p %Z")
                    await log_channel.send(
                        f"Private channel report-001-{str(user_id)[-4:]} for {target_user.name} (ID: {user_id}) "
                        f"in category {CATEGORY_ID} deleted at ({date_str}) ({time_str}) due to /reset by {interaction.user.name}"
                    )
            del user_private_channels[user_id]
        except Exception as e:
            wert_user = await bot.fetch_user(WERT_USER_ID)
            if wert_user:
                await wert_user.send(f"Error deleting existing private channel for {target_user.name} (ID: {user_id}) in category {CATEGORY_ID} during /reset by {interaction.user.name}: {str(e)}")
    # Create new private status channel
    category = guild.get_channel(int(CATEGORY_ID))
    if not category:
        wert_user = await bot.fetch_user(WERT_USER_ID)
        if wert_user:
            await wert_user.send(f"Error: Category {CATEGORY_ID} not found for creating private channel for {target_user.name} (ID: {user_id}) during /reset by {interaction.user.name}")
        await interaction.followup.send("Error: Category for private channels not found. Please contact an admin.", ephemeral=True)
        return
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        target_user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_messages=True,
            read_message_history=True,
            use_application_commands=True
        )
    }
    try:
        private_channel = await guild.create_text_channel(
            f"report-001-{str(user_id)[-4:]}",
            overwrites=overwrites,
            category=category
        )
        user_private_channels[user_id] = private_channel.id
        await private_channel.send(
            f"{target_user.mention}, you have been clocked in via /reset by {interaction.user.mention}. "
            "You can clock out without submitting a report for this session. "
            "Optionally, submit a Status Report with an attachment if desired."
        )
    except Exception as e:
        wert_user = await bot.fetch_user(WERT_USER_ID)
        if wert_user:
            await wert_user.send(f"Error creating private channel for {target_user.name} (ID: {user_id}) in category {CATEGORY_ID} during /reset by {interaction.user.name}: {str(e)}")
        await interaction.followup.send("Error creating private status channel for the user. Please contact an admin.", ephemeral=True)
        return
    # Log reset clock-in
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        clock_dt = datetime.now(CDT)
        date_str = clock_dt.strftime("%Y-%m-%d")
        time_str = clock_dt.strftime("%I:%M:%S %p %Z")
        await log_channel.send(f"<@{user_id}> clocked in via /reset (no report required) by {interaction.user.name} at ({date_str}) ({time_str})")
    await interaction.followup.send(
        f"{target_user.mention} has been clocked in via /reset! They can clock out without a report in their private status channel: {private_channel.mention}.",
        ephemeral=True
    )

# Add commands to the bot
bot.tree.add_command(checkstate)
bot.tree.add_command(reset)

# Run the bot using the token from Render environment variables
bot.run(os.getenv('DISCORD_BOT_TOKEN'))
