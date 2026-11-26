<b>Functional view : </b>

This first release delivers a working data collector for the port of Nansha, one of the main gateways for Chinese exports toward Europe and the Mediterranean. It regularly checks the port's published information on vessels and port activity, keeps a clean history, and records only what has genuinely changed, so you are not flooded with duplicates or cosmetic updates. The starting reference data (ports, terminals, known routes) has been checked by hand, so the first alerts and comparisons rest on reliable ground. The same approach can then be extended to other Chinese ports, one collector at a time. Setup instructions are included so the service can be running on its own, without manual intervention, within a short time.

<b>Technical view : </b>

<b>Database:</b> a Postgres schema with its migration, hosted on Nhost, plus a seed file of reference data verified by hand.
<b>Nansha collector:</b> it fetches the port's pages and parses them with tolerant HTML logic. Instead of relying on fixed column positions, it matches table headers by name, so a layout tweak on the source site does not silently break extraction.
<b>Deduplication:</b> each record is hashed on its normalized content (not on raw HTML), so only real changes produce a new row and noise like whitespace, timestamps or ads is ignored.
<b>Tests:</b> parser fixtures built from real page samples, so regressions are caught when the source markup changes.
<b>Automation:</b> a GitHub Actions workflow runs the collector on a schedule, with configuration through environment variables (.env.example provided).
