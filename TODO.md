# TURA / NEXUS follow-up

- [ ] Run the NEXUS route tests, JavaScript syntax check, and full Python regression suite from the TURA project root; resolve all failures.
- [ ] Browser-test the PWA install/offline path and local vault/message/task persistence.
- [ ] Test WebRTC with two distinct devices and multiple network types; document whether each can connect without a relay.
- [ ] For reliable cross-country connections, decide whether to host a TURN relay. Without one, some NAT/firewall combinations will fail.
- [ ] Consider shared accounts, room membership/revocation, passphrase recovery, and a consented signaling service only if the team later accepts hosting.
- [ ] Treat code upload, execution, AI review, network topology, security scanning, and file transfer as separate future work. Safe code execution needs an isolated runner; the current local browser app does not execute submitted code.
- [ ] Before using TURA with real passengers, payments, or location data, replace the documented demo payment/tracking paths and complete security, privacy, backup, and deployment reviews.
