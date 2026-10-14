# Credential inventory

Every secret the project has or has planned. A credential not in this table should not exist.

| Credential | Lives | Read by | Rotation | State |
| --- | --- | --- | --- | --- |
| Owner sign-in to Azure | Workstation token cache | Operator | New sign-in | In use |
| Platform deployment key and certificate | Workstation, outside the repository | Operator | New key pair and a bootstrap apply. [Procedure](../runbooks/network-foundation.md#rotate-a-certificate) written, not yet run | In use |
| Target deployment key and certificate | Same | Operator | Same | Same |
| Bootstrap state | Workstation, local file. A copy in its own container in the platform state account | Operator. The platform identity can read the copy, which holds identifiers and no secret | Not a secret to rotate | In use |
| Platform and target state | One storage account per root | That root's identity, and a subscription administrator | Not rotated. Access is by role | In use |
| Operator's GitHub account | GitHub | Operator | Account sign-in settings | In use |
| Mesh VPN auth key | Supplied at provisioning. A spent copy stays in the VM's custom data and in platform state | The orchestrator, once | Single use. A new key per rebuild | Spent |
| Mesh node signing keys | The operator's two signing devices | The mesh VPN client on each device | Remove the device as a signer and add another | In use |
| Mesh signing disablement secrets | With the operator, off the workstation | Operator | Turn signing off and on again, which issues new secrets | In use. One is enough to turn signing off |
| Mesh node key | Orchestrator | Root on the orchestrator | Re-enroll with a new auth key. [Procedure](../runbooks/platform-compute.md#mesh-vpn-node-key) run once | In use |
| Operator SSH key | Workstation, outside the repository, used for this project only | Operator | New key, swapped on the running VMs. [Procedure](../runbooks/platform-compute.md#operator-ssh-key) run once | In use |
| Feed SSH key, orchestrator to worker and targets | Orchestrator, generated there at first boot | The administrator account and root on the orchestrator | New key, pushed from the orchestrator. [Procedure](../runbooks/platform-compute.md#feed-key) run once | In use, trusted by the worker |
| Cluster token and administrator kubeconfig | Orchestrator | Root on the orchestrator | Cluster token rotation. [Procedure](../runbooks/platform-compute.md#cluster-token) run once | In use |
| Job token for tool calls | Issued per job by the dispatch step. The tool service keeps a SHA-256 digest, in memory. On the worker it sits in the job's recipe file and in the agent's session database, both in the unit's private `/tmp` | One worker session | Revoked when the job ends, and expires regardless. A restart of the tool service ends every token | Written for token validation and revocation in the tool service, which is not deployed. Token issuance is not implemented ([0013](../decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md)) |
| Dispatch step's service account token | Projected into the dispatch pod by the cluster, with the tool service as its audience and a short lifetime | The dispatch step. It authenticates requests to the registration listener only | Issued again by the cluster before it expires | Decided ([0013](../decisions/0013-a-token-per-job-and-no-cloud-identity-yet.md)), milestone 3. The tool service's check of it is written |
| Dispatch SSH key, orchestrator to worker | `orchestration` namespace, as a secret | The dispatch step | New key pair, public half replaced on the worker | Decided ([0012](../decisions/0012-dispatch-over-ssh-with-a-forced-command.md)), milestone 3 |
| Worker log export key | Orchestrator | The unit that pulls the worker's journal | New key pair, public half replaced on the worker | Decided ([0014](../decisions/0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)), milestone 3 |
| Tool service server certificate, self-signed, and its key | Orchestrator. The worker holds a copy of the certificate | Root on the orchestrator, and the tool service | New key and certificate, new copy on the worker | Written: `platform/tool-service/make-cert.sh` makes it ([0016](../decisions/0016-a-pinned-certificate-an-offline-caller-check-and-a-line-limit.md)). Not created yet |
| NetBox administrator, database, and consumer token | Target VMs | The target, and the orchestrator for seeding | Reseeded with each rebuild | Milestone 4 |
| Repository app key | `change` namespace | PR broker | App key rotation | Open, milestone 5 |

The cluster's public service account signing keys are not secret, but the tool service's copy of them needs to stay current. The copy is the key set the API serves at `/openid/v1/jwks`. The service uses it to verify the dispatch step's token. A copy that is stale after a signing key rotation causes registration to fail.
