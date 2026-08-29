# Patch summary

- AI Server base: v25.9.16.5.18.1
- Release package: v25.9.16.5.19
- openedx-connector-plugin: included from AI Server package
- openedx-unit-reset-plugin: v0.4.14.5 overlay
- frontend-app-learning patch: UnitResetButton reloads unit iframe after quiz-session start/reset

Important: this does not force-enable Submit. It only ensures the LMS XBlock iframe is rendered after the timer session becomes ACTIVE.
