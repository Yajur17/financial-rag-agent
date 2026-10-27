import sys
from pathlib import Path
from lang import run_agent

# A question that needs TWO tools would show the loop running twice; a normal one
# runs the loop once (model -> tool -> model). Override from the CLI:
#   python3 scripts/trace_agent.py "which holding is highest in July?"
QUESTION = sys.argv[1] if len(sys.argv) > 1 else "how much did I invest in all mutual funds?"
LOG_PATH = Path(__file__).resolve().parent.parent / "eval" / "agent_trace.log"

answer, rows = run_agent(QUESTION, log_path=str(LOG_PATH))

print(f"\nQUESTION: {QUESTION}")
print(f"ANSWER:   {answer}")
print(f"\nFull request/response trace written to:\n{LOG_PATH}")
