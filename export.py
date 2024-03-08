import subprocess
import os

def run_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
    output, error = process.communicate()
    return output.strip(), error.strip(), process.returncode

def main():
    dependencies = ['curl', 'gzip', 'jq']
    
    for program in dependencies:
        _, _, return_code = run_command(f'command -v {program}')
        if return_code != 0:
            print(f"Couldn't find dependency: {program}. Aborting.")
            exit(1)

    CURL = run_command('command -v curl')[0]
    GZIP = run_command('command -v gzip')[0]
    JQ = run_command('command -v jq')[0]

    if 'RUNNING_IN_DOCKER' in os.environ:
        with open("/app/pbs_exporter.conf", "r") as conf_file:
            exec(conf_file.read())
    else:
        credentials_directory = os.environ.get("CREDENTIALS_DIRECTORY", "")
        creds_path = os.path.join(credentials_directory, "creds")
        if not os.path.exists(creds_path):
            print(f"Credentials file not found: {creds_path}. Aborting.")
            exit(1)

        with open(creds_path, "r") as creds_file:
            exec(creds_file.read())

    if not all([PBS_API_TOKEN_NAME, PBS_API_TOKEN, PBS_URL, PUSHGATEWAY_URL]):
        print("One or more required environment variables are empty. Aborting.")
        exit(1)

    AUTH_HEADER = f"Authorization: PBSAPIToken={PBS_API_TOKEN_NAME}:{PBS_API_TOKEN}"

    pbs_json, _, _ = run_command(f'{CURL} --silent --fail --show-error --compressed --header "{AUTH_HEADER}" "{PBS_URL}/api2/json/status/datastore-usage"')

    parsed_stores, _, _ = run_command(f'echo "{pbs_json}" | {JQ} --raw-output \'.data[] | select(.avail !=-1) | .store\'')

    if not parsed_stores:
        print("Couldn't parse any store from the PBS API. Aborting.")
        exit(1)

    for STORE in parsed_stores.split('\n'):
        store_status_json, _, _ = run_command(f'{CURL} --silent --fail --show-error --compressed --header "{AUTH_HEADER}" "{PBS_URL}/api2/json/admin/datastore/{STORE}/snapshots"')

        if not store_status_json:
            print(f"Couldn't parse any snapshot status from the PBS API for store={STORE}. Aborting.")
            exit(1)

        snapshot_count_value = run_command(f'echo "{store_status_json}" | {JQ} \'.data | length\'')[0]

        unique_vm_ids, _, _ = run_command(f'echo "{store_status_json}" | {JQ} \'.data | unique_by(."backup-id") | .[]."backup-id"\'')
        if not unique_vm_ids:
            print("Couldn't parse any VM IDs from the PBS API. Aborting.")
            exit(1)

        pbs_snapshot_vm_count_list = ""
        for VM_ID in unique_vm_ids.split('\n'):
            snapshot_count_vm_value = run_command(f'echo "{store_status_json}" | {JQ} "reduce (.data[] | select(.\"backup-id\" == {VM_ID}) | .\"backup-id\") as $i (0;.+=1)"')[0]

            pbs_snapshot_vm_count_list += f'pbs_snapshot_vm_count {{host="{HOSTNAME}", store="{STORE}", vm_id={VM_ID}}} {snapshot_count_vm_value}\n'

        backup_stats = f'''\
# HELP pbs_available The available bytes of the underlying storage.
# TYPE pbs_available gauge
# HELP pbs_size The size of the underlying storage in bytes.
# TYPE pbs_size gauge
# HELP pbs_used The used bytes of the underlying storage.
# TYPE pbs_used gauge
# HELP pbs_snapshot_count The total number of backups.
# TYPE pbs_snapshot_count gauge
# HELP pbs_snapshot_vm_count The total number of backups per VM.
# TYPE pbs_snapshot_vm_count gauge
pbs_available {{host="{HOSTNAME}", store="{STORE}"}} {parsed_backup_stats[0]}
pbs_size {{host="{HOSTNAME}", store="{STORE}"}} {parsed_backup_stats[1]}
pbs_used {{host="{HOSTNAME}", store="{STORE}"}} {parsed_backup_stats[2]}
pbs_snapshot_count {{host="{HOSTNAME}", store="{STORE}"}} {snapshot_count_value}
{pbs_snapshot_vm_count_list}
'''

        _, _, _ = run_command(f'echo "{backup_stats}" | {GZIP} | {CURL} --silent --fail --show-error --header "Content-Encoding: gzip" --data-binary @- "{PUSHGATEWAY_URL}/metrics/job/pbs_exporter/host/{HOSTNAME}/store/{STORE}"')

if __name__ == "__main__":
    main()
