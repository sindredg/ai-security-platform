# NetBox image scans

The SBOM and the vulnerability report of each NetBox pin that milestone 8's [applicability record](../../worklogs/0008-exercise-3-vulnerable-image.md#the-applicability-record) reads. The targets pipeline's "NetBox image scan" wrote them in [targets #20](https://github.com/sindredg/ai-security-platform-test/pull/20), and GitHub deletes its artifacts on 2027-01-30. These are the artifacts' files, compressed with `gzip -9 -n`.

| Pin | Run | File | SHA-256 of the file before compression |
| --- | --- | --- | --- |
| `v4.7.3-5.1.1` | `41330786209` | `v4.7.3-5.1.1.sbom.cdx.json.gz` | `381f1c30b6e2553888f4ef9ab362c0c3b7d72f0989b25b5e5d620e9108467841` |
| `v4.7.3-5.1.1` | `41330786209` | `v4.7.3-5.1.1.vulnerabilities.json.gz` | `5e6383332504afde5411d006cd502ea1f1344714f58c0edbb5a0a06276d262a7` |
| `v4.7.4-5.1.1` | `41330977955` | `v4.7.4-5.1.1.sbom.cdx.json.gz` | `d8d4da4a66a695637fff5005003d2ba561c4d22a1830e2ecd6173bd4a2e8ca8d` |
| `v4.7.4-5.1.1` | `41330977955` | `v4.7.4-5.1.1.vulnerabilities.json.gz` | `9d7620802f87614069d8ce423cf615cf14aac02227dec7c6e5a4f10c3e760db7` |

To read one, and to check it against its row:

```bash
gzip -dc v4.7.4-5.1.1.sbom.cdx.json.gz | sha256sum
gzip -dc v4.7.4-5.1.1.vulnerabilities.json.gz | python3 -I -m json.tool | less
```

The report script in the targets repository judges a report and its SBOM against a pin: `python3 -I .github/scripts/netbox-image-report.py REPORT IMAGE_ID SBOM`.
