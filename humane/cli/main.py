"""Humane CLI — the command interface."""

import click
from humane import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="Humane")
@click.pass_context
def cli(ctx):
    """Humane — human behavioral middleware for AI agents."""
    if ctx.invoked_subcommand is None:
        from humane.cli.dashboard import run_dashboard
        run_dashboard()


@cli.command()
def init():
    """Set up a new Humane agent."""
    from humane.cli.wizard import run_wizard
    run_wizard()


@cli.command()
def demo():
    """See Humane in action — simulates 6 hours of idle time."""
    from humane.cli.demo import run_demo
    run_demo()


@cli.command()
def status():
    """Show current agent state."""
    from humane.conductor import Conductor
    from rich.console import Console
    from rich.table import Table

    console = Console()
    try:
        conductor = Conductor()
        state = conductor.get_state_snapshot()
        queue = conductor.get_hold_queue()

        table = Table(title="HumanState", show_header=True, header_style="bold yellow")
        table.add_column("Dimension", style="white")
        table.add_column("Value", style="bold")
        table.add_column("Bar", style="yellow")

        for dim, val in state.items():
            if dim == "mood":
                bar_len = int(abs(val) * 20)
                bar = ("━" * bar_len) if val >= 0 else ("━" * bar_len)
                color = "green" if val >= 0 else "red"
                table.add_row(dim, f"{val:+.2f}", f"[{color}]{'█' * bar_len}{'░' * (20 - bar_len)}[/]")
            else:
                bar_len = int(val * 20)
                table.add_row(dim, f"{val:.2f}", f"[yellow]{'█' * bar_len}{'░' * (20 - bar_len)}[/]")

        console.print(table)
        console.print(f"\n[dim]Hold queue: {len(queue)} pending actions[/]")
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        console.print("[dim]Run 'humane init' first.[/]")


@cli.command()
@click.argument("action", type=click.Choice(["approve", "reject"]))
@click.argument("hold_id")
def queue(action, hold_id):
    """Manage the hold queue — approve or reject held actions."""
    from humane.conductor import Conductor
    from rich.console import Console

    console = Console()
    conductor = Conductor()

    if action == "approve":
        conductor.approve_hold(hold_id)
        console.print(f"[green]Approved[/] hold item {hold_id[:8]}...")
    else:
        conductor.reject_hold(hold_id)
        console.print(f"[red]Rejected[/] hold item {hold_id[:8]}...")


@cli.command()
def serve():
    """Start the bot(s) + REST API + web dashboard."""
    import asyncio
    import logging
    from pathlib import Path
    from rich.console import Console

    console = Console()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    config_dir = Path.home() / ".humane"
    config_path = None
    if config_dir.exists():
        yamls = list(config_dir.glob("*.yaml"))
        if yamls:
            config_path = str(yamls[0])

    from humane.core.config import HumaneConfig, load_config

    if config_path:
        config = load_config(config_path)
    else:
        config = HumaneConfig()

    # Allow HUMANE_* environment variables to override config values
    config = HumaneConfig.from_env(base=config)

    from humane.conductor import Conductor

    conductor = Conductor(config=config, db_path=config.db_path)

    async def run():
        tasks = []

        # Initialize multi-agent registry
        from humane.multi import AgentRegistry
        registry = AgentRegistry()

        # Start REST API + web dashboard (with multi-agent support)
        from humane.api.server import APIServer
        api = APIServer(conductor, config, registry=registry)
        runner = await api.start(config.api_port)

        agent_count = len(registry.list_agents())
        if agent_count:
            console.print(f"[yellow]◆[/] Multi-agent: [bold]{agent_count} agent(s) loaded[/]")
        console.print(f"[yellow]◆[/] Web dashboard: [bold]http://localhost:{config.api_port}[/]")

        # Start Telegram bot if token is configured
        if config.telegram_bot_token:
            from humane.bot.telegram_bot import HumaneBot
            bot = HumaneBot(config)
            bot.conductor = conductor  # Share the same conductor
            console.print(f"[yellow]◆[/] Telegram bot: [bold]starting...[/]")
            tasks.append(asyncio.create_task(bot.start()))
        else:
            console.print("[dim]No Telegram token -- Telegram bot disabled.[/]")

        # Start WhatsApp bot if configured
        if config.whatsapp_phone_number_id and config.whatsapp_access_token:
            from humane.bot.whatsapp_bot import WhatsAppBot
            from humane.bot.brain import Brain
            from humane.bot.conversation import ConversationEngine
            from humane.bot.scheduler import Scheduler

            conversation = ConversationEngine(
                llm_provider=config.llm_provider,
                llm_model=config.llm_model,
                api_key=config.llm_api_key,
                base_url=config.llm_base_url,
            )
            brain = Brain(conductor, conversation)
            scheduler = Scheduler(brain)

            wa_bot = WhatsAppBot(config, brain, scheduler)
            wa_bot.setup_scheduler()
            api.set_whatsapp_bot(wa_bot)

            # Start scheduler for WhatsApp in background
            asyncio.create_task(scheduler.start())

            console.print(
                f"[yellow]◆[/] WhatsApp bot: [bold]active[/] "
                f"(webhook at /webhook/whatsapp)"
            )
        else:
            console.print("[dim]No WhatsApp credentials -- WhatsApp bot disabled.[/]")

        console.print()
        console.print("[yellow]══════════════════════════════════════════[/]")
        console.print("[bold]  Humane is running.[/]")
        console.print("[dim]  Press Ctrl+C to stop.[/]")
        console.print("[yellow]══════════════════════════════════════════[/]")

        try:
            if tasks:
                await asyncio.gather(*tasks)
            else:
                while True:
                    await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]Shutting down...[/]")
        finally:
            await api.shutdown()
            await runner.cleanup()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


@cli.command()
def quickstart():
    """Generate a quickstart integration example."""
    code = '''from humane import guard

@guard(action_type="send_message", confidence=0.8)
def send_followup(contact_id, message_body):
    """This function only executes if ALL 10 gates return PROCEED.
    If any gate returns HOLD or DEFER, the action enters
    the dashboard queue and you get a notification."""
    print(f"Sending to {contact_id}: {message_body}")

# Try it:
result = send_followup("arjun@designstudio.com", "Following up on our proposal")
print(result)
'''
    click.echo(code)


def _load_conductor():
    """Shared helper: load config and build a Conductor instance."""
    from pathlib import Path
    from humane.core.config import HumaneConfig, load_config
    from humane.conductor import Conductor

    config_dir = Path.home() / ".humane"
    config_path = None
    if config_dir.exists():
        yamls = list(config_dir.glob("*.yaml"))
        if yamls:
            config_path = str(yamls[0])

    if config_path:
        config = load_config(config_path)
    else:
        config = HumaneConfig()

    conductor = Conductor(config=config, db_path=config.db_path)
    return conductor, config


@cli.command(name="export")
@click.option("--output", "-o", default=None, help="Output file path (default: humane-export-{date}.json)")
def export_cmd(output):
    """Export all agent data to a JSON file."""
    import datetime
    import json
    from rich.console import Console

    console = Console()

    try:
        conductor, config = _load_conductor()
    except Exception as e:
        console.print(f"[red]Error loading agent:[/] {e}")
        console.print("[dim]Run 'humane init' first.[/]")
        return

    from humane.io import export_bundle

    bundle = export_bundle(conductor, config)

    if output is None:
        date_str = datetime.date.today().isoformat()
        output = f"humane-export-{date_str}.json"

    with open(output, "w") as f:
        json.dump(bundle, f, default=str, indent=2)

    entity_count = len(bundle.get("entities", []))
    goal_count = len(bundle.get("goals", []))
    memory_count = len(bundle.get("memories", []))
    value_count = len(bundle.get("values", []))

    console.print(f"[green]Exported[/] to [bold]{output}[/]")
    console.print(
        f"  [dim]{entity_count} entities, {goal_count} goals, "
        f"{memory_count} memories, {value_count} values[/]"
    )


@cli.command(name="import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--mode", "-m", type=click.Choice(["replace", "merge"]), default="merge", help="Import mode (default: merge)")
def import_cmd(file, mode):
    """Import agent data from a JSON file."""
    import json
    from rich.console import Console

    console = Console()

    try:
        conductor, config = _load_conductor()
    except Exception as e:
        console.print(f"[red]Error loading agent:[/] {e}")
        console.print("[dim]Run 'humane init' first.[/]")
        return

    try:
        with open(file, "r") as f:
            bundle = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON:[/] {e}")
        return
    except Exception as e:
        console.print(f"[red]Error reading file:[/] {e}")
        return

    from humane.io import import_bundle

    if mode == "replace":
        if not click.confirm("Replace mode will clear all existing data. Continue?"):
            console.print("[yellow]Cancelled.[/]")
            return

    result = import_bundle(conductor, config, bundle, merge_mode=mode)

    if result["errors"]:
        for err in result["errors"]:
            console.print(f"  [red]Error:[/] {err}")
        return

    imp = result["imported"]
    console.print(f"[green]Imported[/] from [bold]{file}[/] (mode={mode})")
    console.print(
        f"  [dim]{imp.get('entities', 0)} entities, {imp.get('goals', 0)} goals, "
        f"{imp.get('memories', 0)} memories, {imp.get('values', 0)} values[/]"
    )
    if result["skipped"]:
        console.print(f"  [yellow]Skipped {result['skipped']} duplicates[/]")


# ------------------------------------------------------------------
# Multi-agent management
# ------------------------------------------------------------------

@cli.group()
def agents():
    """Manage multiple Humane agents."""
    pass


@agents.command(name="list")
def agents_list():
    """Show all registered agents."""
    from rich.console import Console
    from rich.table import Table
    from humane.multi import AgentRegistry

    console = Console()
    try:
        registry = AgentRegistry()
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        return

    agent_list = registry.list_agents()
    if not agent_list:
        console.print("[dim]No agents registered. Create one with:[/] humane agents create <name>")
        return

    table = Table(title="Humane Agents", show_header=True, header_style="bold yellow")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status", style="green")
    table.add_column("DB Path", style="dim")

    for agent in agent_list:
        table.add_row(
            agent["id"],
            agent["name"],
            agent["status"],
            agent["db_path"],
        )

    console.print(table)


@agents.command(name="create")
@click.argument("name")
@click.option("--personality", default=None, help="Bot personality preset")
@click.option("--llm-provider", default=None, help="LLM provider (anthropic, openai, etc.)")
def agents_create(name, personality, llm_provider):
    """Create a new Humane agent."""
    from rich.console import Console
    from humane.multi import AgentRegistry

    console = Console()
    try:
        registry = AgentRegistry()
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        return

    overrides = {}
    if personality:
        overrides["bot_personality"] = personality
    if llm_provider:
        overrides["llm_provider"] = llm_provider

    try:
        agent_id = registry.create_agent(name, config_overrides=overrides)
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}")
        return

    console.print(f"[green]Created[/] agent [bold]{name}[/] (id={agent_id})")


@agents.command(name="delete")
@click.argument("name_or_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def agents_delete(name_or_id, yes):
    """Delete a Humane agent and its data."""
    from rich.console import Console
    from humane.multi import AgentRegistry

    console = Console()
    try:
        registry = AgentRegistry()
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        return

    # Resolve by name or id
    try:
        agent_id = registry.resolve_agent_id(name_or_id)
    except KeyError:
        console.print(f"[red]Agent not found:[/] {name_or_id}")
        return

    if not yes:
        if not click.confirm(f"Delete agent '{name_or_id}' (id={agent_id})? This removes all data."):
            console.print("[yellow]Cancelled.[/]")
            return

    try:
        registry.delete_agent(agent_id)
    except KeyError:
        console.print(f"[red]Agent not found:[/] {agent_id}")
        return

    console.print(f"[green]Deleted[/] agent {agent_id}")


# ------------------------------------------------------------------
# Encryption management
# ------------------------------------------------------------------

@cli.command(name="encrypt-config")
def encrypt_config_cmd():
    """Encrypt all sensitive fields in the existing config file."""
    from pathlib import Path
    from rich.console import Console
    from humane.core.config import (
        HumaneConfig,
        SENSITIVE_FIELDS,
        _ENC_PREFIX,
        load_config,
        save_config,
        get_default_config_path,
    )

    console = Console()

    config_dir = Path.home() / ".humane"
    config_path = None
    if config_dir.exists():
        yamls = list(config_dir.glob("*.yaml"))
        if yamls:
            config_path = str(yamls[0])

    if not config_path:
        console.print("[red]No config file found.[/] Run 'humane init' first.")
        return

    try:
        # Load will decrypt if already encrypted; save will re-encrypt.
        config = load_config(config_path)
        save_config(config, config_path)
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        return

    encrypted_fields = [f for f in SENSITIVE_FIELDS if getattr(config, f, "")]
    if encrypted_fields:
        console.print(
            f"[green]Encrypted[/] {len(encrypted_fields)} sensitive field(s) "
            f"in [bold]{config_path}[/]: {', '.join(sorted(encrypted_fields))}"
        )
    else:
        console.print("[dim]No sensitive fields with values to encrypt.[/]")

    from humane.encryption import get_encryption_manager
    mgr = get_encryption_manager()
    console.print(f"[dim]Encryption backend: {mgr.backend}[/]")


@cli.command(name="rotate-key")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def rotate_key_cmd(yes):
    """Generate a new encryption key and re-encrypt all data."""
    from pathlib import Path
    from rich.console import Console
    from humane.encryption import EncryptionManager, reset_encryption_manager

    console = Console()

    if not yes:
        if not click.confirm(
            "This will generate a new encryption key and re-encrypt all "
            "config and database content. Continue?"
        ):
            console.print("[yellow]Cancelled.[/]")
            return

    # 1. Capture old manager before rotation.
    old_manager = EncryptionManager()

    # 2. Generate new key.
    new_manager = EncryptionManager()
    new_manager.generate_new_key()
    reset_encryption_manager()

    console.print("[green]Generated new encryption key.[/]")

    # 3. Re-encrypt config file.
    config_dir = Path.home() / ".humane"
    config_path = None
    if config_dir.exists():
        yamls = list(config_dir.glob("*.yaml"))
        if yamls:
            config_path = str(yamls[0])

    if config_path:
        try:
            from humane.core.config import load_config, save_config, SENSITIVE_FIELDS, _ENC_PREFIX

            import yaml as _yaml
            with open(config_path, "r") as f:
                raw = _yaml.safe_load(f) or {}

            # Decrypt sensitive fields with the OLD key.
            for field in SENSITIVE_FIELDS:
                value = raw.get(field)
                if value and isinstance(value, str) and value.startswith(_ENC_PREFIX):
                    try:
                        raw[field] = old_manager.decrypt(value[len(_ENC_PREFIX):])
                    except Exception:
                        pass  # leave as-is if it cannot be decrypted

            # Now load normally (new manager is the default) and save.
            from dataclasses import fields as dc_fields
            from humane.core.config import HumaneConfig, validate_config

            valid = {fld.name for fld in dc_fields(HumaneConfig)}
            filtered = {k: v for k, v in raw.items() if k in valid}
            config = HumaneConfig(**filtered)
            validate_config(config)
            save_config(config, config_path)
            console.print(f"[green]Re-encrypted[/] config: {config_path}")
        except Exception as e:
            console.print(f"[red]Config re-encryption failed:[/] {e}")

    # 4. Re-encrypt database content.
    try:
        conductor, config = _load_conductor()
        store = conductor.store

        if config.encrypt_data_at_rest:
            # Re-encrypt conversations.
            rows = store.conn.execute("SELECT id, content FROM conversations").fetchall()
            for row in rows:
                try:
                    plain = old_manager.decrypt(row["content"])
                except Exception:
                    plain = row["content"]
                new_ct = new_manager.encrypt(plain)
                store.conn.execute(
                    "UPDATE conversations SET content = ? WHERE id = ?",
                    (new_ct, row["id"]),
                )

            # Re-encrypt memories.
            rows = store.conn.execute("SELECT id, content FROM memories").fetchall()
            for row in rows:
                try:
                    plain = old_manager.decrypt(row["content"])
                except Exception:
                    plain = row["content"]
                new_ct = new_manager.encrypt(plain)
                store.conn.execute(
                    "UPDATE memories SET content = ? WHERE id = ?",
                    (new_ct, row["id"]),
                )

            store.conn.commit()
            console.print("[green]Re-encrypted[/] database content (conversations + memories).")
        else:
            console.print("[dim]encrypt_data_at_rest is disabled -- skipping database re-encryption.[/]")
    except Exception as e:
        console.print(f"[red]Database re-encryption failed:[/] {e}")

    console.print("[green]Key rotation complete.[/]")
