import json
import subprocess
import sys
import os

THRESHOLD = 80.0

def main():
    print("Running CI Gate for CIRA Accuracy Suite...")
    
    # 1. Run the runner
    print("Executing runner.py...")
    runner_path = os.path.join(os.path.dirname(__file__), "runner.py")
    res = subprocess.run([sys.executable, runner_path], capture_output=False)
    if res.returncode != 0:
        print("Runner failed to execute successfully.")
        sys.exit(1)
        
    # 2. Run the scorecard
    print("Executing scorecard.py...")
    scorecard_path = os.path.join(os.path.dirname(__file__), "scorecard.py")
    res = subprocess.run([sys.executable, scorecard_path], capture_output=False)
    if res.returncode != 0:
        print("Scorecard generation failed.")
        sys.exit(1)
        
    # 3. Read results and enforce threshold
    results_path = os.path.join(os.path.dirname(__file__), "results.json")
    if not os.path.exists(results_path):
        print("results.json not found!")
        sys.exit(1)
        
    with open(results_path, "r") as f:
        results = json.load(f)
        
    total = len(results)
    passes = sum(1 for r in results if r["pass"])
    pass_rate = (passes / total) * 100 if total > 0 else 0
    
    # Also enforce 100% on hallucination traps
    hallucination_fails = [r for r in results if r["bucket"] == "hallucination" and not r["pass"]]
    
    print("\n" + "="*40)
    print(f"CI Gate Results: {pass_rate:.1f}% Accuracy")
    print("="*40)
    
    failed = False
    
    if pass_rate < THRESHOLD:
        print(f"❌ FAIL: Overall accuracy {pass_rate:.1f}% is below threshold {THRESHOLD}%")
        failed = True
    else:
        print(f"✅ PASS: Overall accuracy {pass_rate:.1f}% meets threshold {THRESHOLD}%")
        
    if hallucination_fails:
        print(f"❌ FAIL: Failed {len(hallucination_fails)} hallucination traps! These must be 100% accurate.")
        failed = True
    else:
        print("✅ PASS: 100% on hallucination traps.")
        
    if failed:
        sys.exit(1)
        
    print("CI Gate Passed! 🎉")
    sys.exit(0)

if __name__ == "__main__":
    main()
