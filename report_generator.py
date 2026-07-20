import json

def generate_report(query: str, findings: list) -> tuple[str, str]:
    """
    Generate a clean research report in Markdown and JSON formats based strictly on extracted findings.
    Never invents facts, summaries, or sources.
    
    Args:
        query: The user's research task.
        findings: List of dictionaries containing 'title', 'url', and 'snippet'.
        
    Returns:
        Tuple of (markdown_string, json_string).
    """
    has_findings = bool(findings)
    status = "Complete - Sources compiled." if has_findings else "Incomplete - insufficient sources found."
    
    # 1. Build JSON Dictionary
    report_dict = {
        "task_objective": query,
        "completion_status": status,
        "summary": "",
        "key_findings": [],
        "sources_list": []
    }
    
    # 2. Build Markdown String
    md_lines = []
    md_lines.append(f"# Research Report")
    md_lines.append(f"**Task Objective:** {query}")
    md_lines.append(f"**Completion Status:** {status}")
    md_lines.append("")
    
    if has_findings:
        # Summary (use first 2 snippets as a combined raw summary)
        md_lines.append("## Overview")
        overview_texts = [f["snippet"] for f in findings[:2] if f.get("snippet")]
        summary_text = "\n\n".join(overview_texts)
        md_lines.append(summary_text)
        report_dict["summary"] = summary_text
        md_lines.append("")
        
        # Key Findings
        md_lines.append("## Key Findings")
        for f in findings:
            snippet = f.get("snippet", "")
            if snippet:
                md_lines.append(f"- {snippet}")
                report_dict["key_findings"].append(snippet)
        md_lines.append("")
        
        # Sources List
        md_lines.append("## Sources")
        for f in findings:
            title = f.get("title", "Untitled")
            url = f.get("url", "")
            md_lines.append(f"- [{title}]({url})")
            report_dict["sources_list"].append({"title": title, "url": url})
            
    else:
        md_lines.append("No findings were collected for this task.")
        
    markdown_str = "\n".join(md_lines)
    json_str = json.dumps(report_dict, indent=2)
    
    return markdown_str, json_str
