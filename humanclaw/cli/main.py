"""HumanClaw CLI — the command interface."""

import click
from humanclaw import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="HumanClaw")
@click.pass_context
def cli(ctx):
    """HumanClaw — human behavioral middleware for AI agents."""
    if ctx.invoked_subcommand is None:
        from humanclaw.cli.dashboard import run_dashboard
        run_dashboard()


@cli.command()
def init():
    """Set up a new HumanClaw agent."""
    from humanclaw.cli.wizard import run_wizard
    run_wizard()


@cli.command()
def demo():
    """See HumanClaw in action — simulates 6 hours of idle time."""
    from humanclaw.cli.demo import run_demo
    run_demo()


@cli.command()
def status():
    """Show current agent state."""
    from humanclaw.conductor import Conductor
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
        console.print("[dim]Run 'humanclaw init' first.[/]")


@cli.command()
@click.argument("action", type=click.Choice(["approve", "reject"]))
@click.argument("hold_id")
def queue(action, hold_id):
    """Manage the hold queue — approve or reject held actions."""
    from humanclaw.conductor import Conductor
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
def quickstart():
    """Generate a quickstart integration example."""
    code = '''from humanclaw import guard

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
