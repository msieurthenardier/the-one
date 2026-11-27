Route (mission and flight, sortie, or squawk number):

Read [CONTRIBUTING.md](https://github.com/msieurthenardier/the-one/blob/main/CONTRIBUTING.md). A pull request that was not built through the Mission Control plugin is closed without merge.

- [ ] Planned and built with the Mission Control plugin
- [ ] Artifacts included
  - Flight or sortie: `flight.md`, `legs/`, `flight-log.md`, `flight-briefing.md`, `flight-debrief.md`
  - Squawk: the completed squawk file with its sign-off
- [ ] Independent Reviewer sign-off recorded (not the implementing agent)
- [ ] `make gate` (or the relevant `scripts/run-tests.sh` lanes) run on Linux or WSL2. Result:
- [ ] `ruff check` and `ruff format --check` clean
