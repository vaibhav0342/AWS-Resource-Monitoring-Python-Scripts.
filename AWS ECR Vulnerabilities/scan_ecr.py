import subprocess
import json
import csv

class Vulnerability:
    def __init__(self, repo_name="", pack_name="", pack_version="", image_id="", uri=""):
        self.repo_name = repo_name
        self.pack_name = pack_name
        self.pack_version = pack_version
        self.image_id = image_id
        self.uri = uri

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running: {cmd}\n{result.stderr}")
        return None
    return result.stdout.strip()

def get_all_repos():
    output = run_cmd("aws ecr describe-repositories")
    if not output: return []
    repos = json.loads(output).get("repositories", [])
    print(f'Number of repos: {len(repos)}')
    return repos

def get_latest_img_digest(repo_name):
    cmd = f"aws ecr describe-images --repository-name {repo_name} --query 'sort_by(imageDetails,& imagePushedAt)[-1].imageDigest' --output text"
    return run_cmd(cmd)

def start_scanning(repo_name, image_digest):
    cmd = f"aws ecr start-image-scan --repository-name {repo_name} --image-id imageDigest={image_digest}"
    return run_cmd(cmd)

def wait_scan_results(repo_name, image_digest):
    cmd = f"aws ecr wait image-scan-complete --repository-name {repo_name} --image-id imageDigest={image_digest}"
    return run_cmd(cmd)

def get_scan_result(repo_name, image_digest):
    cmd = f"aws ecr describe-image-scan-findings --repository-name {repo_name} --image-id imageDigest={image_digest}"
    output = run_cmd(cmd)
    return json.loads(output) if output else {}

def finding_vulnerabilities(repo_name, json_result):
    vulns = []
    for result in json_result.get('imageScanFindings', {}).get('findings', []):
        if result.get('severity') == "CRITICAL":
            v = Vulnerability(repo_name=repo_name, uri=result.get('uri', ''))
            for att in result.get("attributes", []):
                if att["key"] == "package_name":
                    v.pack_name = att["value"]
                if att["key"] == "package_version":
                    v.pack_version = att["value"]
            vulns.append(v)
    return vulns

def write_to_csv(vulns):
    if not vulns: return
    with open("repo_with_CRITICAL_issues.csv", 'w', newline='', encoding='utf8') as f:
        writer = csv.writer(f)
        writer.writerow(["Repo","package_name","version","uri"])
        for v in vulns:
            writer.writerow([v.repo_name, v.pack_name, v.pack_version, v.uri])

def main():
    critical_vulns = []
    for repo in get_all_repos():
        repo_name = repo["repositoryName"]
        print(f"\n--- Scanning repo: {repo_name} ---")

        image_digest = get_latest_img_digest(repo_name)
        if not image_digest:
            print(f"⚠️ No images found for {repo_name}")
            continue

        start_scanning(repo_name, image_digest)
        wait_scan_results(repo_name, image_digest)

        result = get_scan_result(repo_name, image_digest)
        if result.get("imageScanStatus", {}).get("status") == "FAILED":
            print(f"❌ Scan failed for {repo_name}")
            continue

        critical_vulns.extend(finding_vulnerabilities(repo_name, result))

    write_to_csv(critical_vulns)
    print(f"\n✅ Total repos with CRITICAL issues: {len(critical_vulns)}")

if __name__ == "__main__":
    main()
