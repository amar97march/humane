"""Quick serve script for preview."""
import asyncio
import logging
from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.core.models import EntityType, MemoryType
from humane.api.server import APIServer

logging.basicConfig(level=logging.INFO)

config = HumaneConfig()
config.db_path = "/tmp/humane_serve.db"
conductor = Conductor(config=config, db_path=config.db_path)

# Seed demo data
conductor.relational.add_entity("arjun", EntityType.PROSPECT)
conductor.relational.add_entity("priya", EntityType.CLIENT)
conductor.relational.add_entity("rahul", EntityType.CLOSE_COLLEAGUE)
conductor.relational.log_interaction("arjun", 0.3, "Sent proposal for design work")
conductor.relational.log_interaction("priya", 0.7, "Positive project kickoff call")
conductor.relational.log_interaction("rahul", 0.5, "Regular sync")
conductor.goal_engine.register_goal("Close DesignStudio deal", expected_value=0.8, milestones_total=5)
conductor.goal_engine.register_goal("Launch Q2 marketing campaign", expected_value=0.6, milestones_total=8)
conductor.memory_decay.add_memory(MemoryType.EPISODIC, "Sent proposal to Arjun at DesignStudio, awaiting response")

api = APIServer(conductor, config)

async def main():
    runner = await api.start(8765)
    print("Humane dashboard: http://localhost:8765")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await runner.cleanup()

asyncio.run(main())
