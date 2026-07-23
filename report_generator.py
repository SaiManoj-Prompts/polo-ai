import json
import re

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
    is_insufficient = len(findings) == 1 and (not findings[0].get("url") or findings[0].get("title") == "Insufficient results")
    has_findings = bool(findings) and not is_insufficient
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
        # Summary
        md_lines.append("## Overview")
        summary_text = f"Based on the research query '{query}', {len(findings)} relevant sources were compiled. The following findings outline key details from these sources."
        md_lines.append(summary_text)
        report_dict["summary"] = summary_text
        md_lines.append("")
        
        # Key Findings
        md_lines.append("## Key Findings")
        for f in findings:
            title = f.get("title", "Untitled").strip()
            url = f.get("url", "").strip()
            snippet = f.get("snippet", "").strip()
            
            if not snippet:
                continue
                
            is_job = "usajobs.gov" in url or "indeed.com" in url or snippet.startswith("Agency: ") or snippet.startswith("Company: ")
            
            if is_job:
                # Safe structured extraction
                lines = snippet.split('\n')
                org_loc_line = lines[0]
                rest = " ".join(lines[1:])
                
                org = ""
                loc = ""
                if " | Location: " in org_loc_line:
                    parts = org_loc_line.split(" | Location: ")
                    org = parts[0].replace("Agency: ", "").replace("Company: ", "").strip()
                    loc = parts[1].strip()
                else:
                    org = org_loc_line.replace("Agency: ", "").replace("Company: ", "").strip()
                
                details = [f"**Title:** {title}"]
                if org and org != "Unknown Agency" and org != "Unknown Company":
                    details.append(f"**Organization:** {org}")
                if loc and loc != "Unknown Location":
                    details.append(f"**Location:** {loc}")
                
                # Pay extraction using strict regex
                pay_match = re.search(r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:to|-)\s*\$[\d,]+(?:\.\d{2})?)?(?:\s*(?:per\s*year|per\s*hour|/yr|/hr))?', rest, re.IGNORECASE)
                if pay_match:
                    details.append(f"**Pay:** {pay_match.group(0)}")
                    
                # Employment Type extraction using strict matching
                emp_types = []
                rest_lower = rest.lower()
                if "temporarypart-time" in rest_lower or "temporary part-time" in rest_lower:
                    emp_types.append("Temporary, part-time")
                elif "temporaryfull-time" in rest_lower or "temporary full-time" in rest_lower:
                    emp_types.append("Temporary, full-time")
                else:
                    for et in ["Full-time", "Part-time", "Internship", "Contract", "Temporary"]:
                        if re.search(rf'\b{et.lower()}\b', rest_lower):
                            emp_types.append(et)
                            
                if emp_types:
                    unique_emp = []
                    for et in emp_types:
                        if et not in unique_emp:
                            unique_emp.append(et)
                    details.append(f"**Employment Type:** {', '.join(unique_emp)}")
                
                details.append(f"**Source:** {url}")
                finding_text = " | ".join(details)
                
            else:
                # Normal article snippet
                if '.' in snippet:
                    first_sentence = snippet.split('.')[0] + '.'
                else:
                    first_sentence = snippet
                    
                first_sentence = first_sentence.strip()
                if len(first_sentence) > 150:
                    first_sentence = first_sentence[:147] + "..."
                    
                finding_text = f"**{title}:** {first_sentence}"
                
            md_lines.append(f"- {finding_text}")
            report_dict["key_findings"].append(finding_text)
        md_lines.append("")
        
        # Sources List
        md_lines.append("## Sources")
        for f in findings:
            title = f.get("title", "Untitled")
            url = f.get("url", "")
            if not url or title == "Insufficient results":
                md_lines.append("- ⚠️ No relevant sources found for this query. Try rephrasing your request or ask about a different topic.")
            else:
                md_lines.append(f"- [{title}]({url})")
                report_dict["sources_list"].append({"title": title, "url": url})
            
    else:
        md_lines.append("No relevant sources were found for this query.")
        
    markdown_str = "\n".join(md_lines)
    json_str = json.dumps(report_dict, indent=2)
    
    return markdown_str, json_str
