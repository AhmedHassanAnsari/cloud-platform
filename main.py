"""CLI entry point for AI DevOps Employee."""

import sys
import os
from src.agents.devops_agent import DevOpsAgent


def main():
    """
    Main CLI entry point for the AI DevOps Employee.
    
    Usage: python main.py
    
    Runs from the current working directory (no path argument needed).
    Starts the DevOps Employee to review the project and detect blockers.
    """
    print("\n🚀 AI DevOps Employee - Project Review & Deployment Preparation")
    print("-" * 60)
    
    cwd = os.getcwd()
    print(f"📂 Working directory: {cwd}\n")
    
    try:
        # Initialize the DevOps Agent
        agent = DevOpsAgent()
        
        # Perform project review
        findings = agent.review_project(cwd)
        
        # Present summary to user
        agent.present_summary(findings)
        
        # Exit with appropriate status
        if findings.ready_for_next_stage:
            print("✅ Review completed successfully. Ready to proceed to next sprint!")
            sys.exit(0)
        else:
            print("⚠️  Please resolve the blockers above before proceeding.")
            sys.exit(1)
    
    except SystemExit as e:
        # Handle user-requested stops
        sys.exit(e.code)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
