"""Show the deterministic H8-to-H9 stale-evidence fixture."""
from scar_core.demo import run_demo


if __name__ == "__main__":
    assessment, story = run_demo()
    print(story)
    print(f"outcome={assessment['outcome']}")
    print(f"unresolved={', '.join(assessment['unresolved_obligations'])}")
    print(f"next={assessment['recommendations'][0]['query_id']}")
    print("unknown or timeout => retain uncertainty and abstain")
