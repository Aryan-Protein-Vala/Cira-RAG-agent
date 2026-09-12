import json
import argparse
import sys
import os

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CIRA Accuracy Scorecard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 2rem; color: #333; max-width: 1000px; margin: 0 auto; }
        h1 { margin-bottom: 0.5rem; }
        .summary { display: flex; gap: 1rem; margin-bottom: 2rem; }
        .card { padding: 1rem; border-radius: 8px; flex: 1; text-align: center; }
        .card h2 { margin: 0; font-size: 2rem; }
        .pass-card { background: #d4edda; color: #155724; }
        .fail-card { background: #f8d7da; color: #721c24; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { padding: 0.75rem; border: 1px solid #ddd; text-align: left; }
        th { background: #f8f9fa; }
        .pass { color: green; font-weight: bold; }
        .fail { color: red; font-weight: bold; }
        .bucket-summary { margin-top: 2rem; }
    </style>
</head>
<body>
    <h1>CIRA LLM Accuracy Scorecard</h1>
    <p>Target: Sandbox Dataset</p>
    
    <div class="summary">
        <div class="card pass-card">
            <h2>{pass_rate}%</h2>
            <p>Overall Accuracy</p>
        </div>
        <div class="card">
            <h2>{total}</h2>
            <p>Total Questions</p>
        </div>
    </div>
    
    <div class="bucket-summary">
        <h3>Accuracy by Category</h3>
        <ul>
            {bucket_html}
        </ul>
    </div>
    
    <h3>Detailed Results</h3>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Bucket</th>
                <th>Question</th>
                <th>Status</th>
                <th>Reason</th>
                <th>LLM Output Snippet</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="results.json")
    parser.add_argument("--output", default="scorecard.html")
    args = parser.parse_args()
    
    in_path = os.path.join(os.path.dirname(__file__), args.input)
    if not os.path.exists(in_path):
        print(f"Results file {in_path} not found.")
        sys.exit(1)
        
    with open(in_path, "r") as f:
        results = json.load(f)
        
    total = len(results)
    if total == 0:
        print("No results to score.")
        sys.exit(1)
        
    passes = sum(1 for r in results if r["pass"])
    pass_rate = round((passes / total) * 100, 1)
    
    # Bucket stats
    buckets = {}
    for r in results:
        b = r["bucket"]
        if b not in buckets:
            buckets[b] = {"total": 0, "pass": 0}
        buckets[b]["total"] += 1
        if r["pass"]:
            buckets[b]["pass"] += 1
            
    bucket_html = ""
    for b, stats in buckets.items():
        rate = round((stats["pass"] / stats["total"]) * 100, 1)
        bucket_html += f"<li><strong>{b.title()}</strong>: {rate}% ({stats['pass']}/{stats['total']})</li>\n"
        
    rows_html = ""
    for r in results:
        status_class = "pass" if r["pass"] else "fail"
        status_text = "PASS" if r["pass"] else "FAIL"
        
        # Truncate final text for display
        final_text = r["final_text"]
        if len(final_text) > 100:
            final_text = final_text[:100] + "..."
            
        rows_html += f"""
        <tr>
            <td>{r["id"]}</td>
            <td>{r["bucket"]}</td>
            <td>{r["question"]}</td>
            <td class="{status_class}">{status_text}</td>
            <td>{r["reason"]}</td>
            <td><code>{final_text}</code></td>
        </tr>
        """
        
    final_html = HTML_TEMPLATE.replace("{pass_rate}", str(pass_rate)) \
                              .replace("{total}", str(total)) \
                              .replace("{bucket_html}", bucket_html) \
                              .replace("{rows_html}", rows_html)
    
    out_path = os.path.join(os.path.dirname(__file__), args.output)
    with open(out_path, "w") as f:
        f.write(final_html)
        
    print(f"Scorecard generated: {out_path} ({pass_rate}% accuracy)")
    
if __name__ == "__main__":
    main()
