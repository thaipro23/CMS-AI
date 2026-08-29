"""Tutor plugin for openedx_unit_reset v0.4.14.

Installs the local Open edX Unit Reset Django plugin from the edx-platform repo
and exposes runtime settings for custom timed practice quiz/reset.

Expected repo layout after copying this AI Server artifact into CMS-FPT:
  /openedx/edx-platform/openedx-unit-reset-plugin/setup.py
  /openedx/edx-platform/openedx-unit-reset-plugin/openedx_unit_reset/...
"""

from tutor import hooks

hooks.Filters.CONFIG_DEFAULTS.add_items([
    ("OPENEDX_UNIT_RESET_PLUGIN_VERSION", "0.4.14"),
    ("UNIT_RESET_DEFAULT_COOLDOWN_SECONDS", "600"),
    ("UNIT_RESET_REQUIRE_COOLDOWN", "true"),
    ("UNIT_RESET_ALLOW_STUDENT_SELF_RESET", "true"),
    ("UNIT_RESET_REQUIRE_ENROLLMENT", "true"),
    ("UNIT_RESET_REQUIRE_UNIT_COURSE_MATCH", "true"),
    ("UNIT_RESET_AUDIT_LOG_ENABLED", "true"),
    ("UNIT_RESET_MAX_RESETS_PER_UNIT", "0"),
    ("UNIT_RESET_USE_LATEST_STUDENTMODULE_MODIFIED_AS_ATTEMPT_TIME", "true"),
    ("UNIT_RESET_QUIZ_TIMER_ENABLED", "true"),
    ("UNIT_RESET_QUIZ_TIMER_DEFAULT_DURATION_SECONDS", "900"),
    ("UNIT_RESET_QUIZ_TIMER_DEFAULT_COOLDOWN_SECONDS", "300"),
    ("UNIT_RESET_QUIZ_TIMER_SERVER_GUARD_ENABLED", "true"),
    ("UNIT_RESET_QUIZ_TIMER_REQUIRE_CONFIG", "true"),
    ("UNIT_RESET_QUIZ_TIMER_SUBMIT_BUTTON_ONLY", "true"),
    ("UNIT_RESET_QUIZ_TIMER_LOCK_COOLDOWN_FROM_EXPIRES_AT", "true"),
    ("UNIT_RESET_QUIZ_TIMER_RUNTIME_LOCK_DELAY_MS", "1500"),
    ("AI_QUIZ_RUNTIME_ALLOWED_ORIGINS", "https://app.cms-test.poly.edu.vn,https://cms-test.poly.edu.vn,https://scms-test.poly.edu.vn"),
])

hooks.Filters.ENV_PATCHES.add_item((
    "openedx-dockerfile-post-python-requirements",
    """
# openedx_unit_reset v0.4.14 — Submit Button Only No Save Hotfix
RUN if [ -d /openedx/edx-platform/openedx-unit-reset-plugin ]; then pip install -e /openedx/edx-platform/openedx-unit-reset-plugin; fi
""",
))

_COMMON_SETTINGS = r'''
# openedx_unit_reset v0.4.14
OPENEDX_UNIT_RESET_PLUGIN_VERSION = "{{ OPENEDX_UNIT_RESET_PLUGIN_VERSION }}"
UNIT_RESET_DEFAULT_COOLDOWN_SECONDS = int("{{ UNIT_RESET_DEFAULT_COOLDOWN_SECONDS }}")
UNIT_RESET_REQUIRE_COOLDOWN = "{{ UNIT_RESET_REQUIRE_COOLDOWN }}".lower() == "true"
UNIT_RESET_ALLOW_STUDENT_SELF_RESET = "{{ UNIT_RESET_ALLOW_STUDENT_SELF_RESET }}".lower() == "true"
UNIT_RESET_REQUIRE_ENROLLMENT = "{{ UNIT_RESET_REQUIRE_ENROLLMENT }}".lower() == "true"
UNIT_RESET_REQUIRE_UNIT_COURSE_MATCH = "{{ UNIT_RESET_REQUIRE_UNIT_COURSE_MATCH }}".lower() == "true"
UNIT_RESET_AUDIT_LOG_ENABLED = "{{ UNIT_RESET_AUDIT_LOG_ENABLED }}".lower() == "true"
UNIT_RESET_MAX_RESETS_PER_UNIT = int("{{ UNIT_RESET_MAX_RESETS_PER_UNIT }}")
UNIT_RESET_USE_LATEST_STUDENTMODULE_MODIFIED_AS_ATTEMPT_TIME = "{{ UNIT_RESET_USE_LATEST_STUDENTMODULE_MODIFIED_AS_ATTEMPT_TIME }}".lower() == "true"
UNIT_RESET_QUIZ_TIMER_ENABLED = "{{ UNIT_RESET_QUIZ_TIMER_ENABLED }}".lower() == "true"
UNIT_RESET_QUIZ_TIMER_DEFAULT_DURATION_SECONDS = int("{{ UNIT_RESET_QUIZ_TIMER_DEFAULT_DURATION_SECONDS }}")
UNIT_RESET_QUIZ_TIMER_DEFAULT_COOLDOWN_SECONDS = int("{{ UNIT_RESET_QUIZ_TIMER_DEFAULT_COOLDOWN_SECONDS }}")
UNIT_RESET_QUIZ_TIMER_SERVER_GUARD_ENABLED = "{{ UNIT_RESET_QUIZ_TIMER_SERVER_GUARD_ENABLED }}".lower() == "true"
UNIT_RESET_QUIZ_TIMER_REQUIRE_CONFIG = "{{ UNIT_RESET_QUIZ_TIMER_REQUIRE_CONFIG }}".lower() == "true"
UNIT_RESET_QUIZ_TIMER_SUBMIT_BUTTON_ONLY = "{{ UNIT_RESET_QUIZ_TIMER_SUBMIT_BUTTON_ONLY }}".lower() == "true"
UNIT_RESET_QUIZ_TIMER_LOCK_COOLDOWN_FROM_EXPIRES_AT = "{{ UNIT_RESET_QUIZ_TIMER_LOCK_COOLDOWN_FROM_EXPIRES_AT }}".lower() == "true"
UNIT_RESET_QUIZ_TIMER_RUNTIME_LOCK_DELAY_MS = int("{{ UNIT_RESET_QUIZ_TIMER_RUNTIME_LOCK_DELAY_MS }}")
AI_QUIZ_RUNTIME_ALLOWED_ORIGINS = "{{ AI_QUIZ_RUNTIME_ALLOWED_ORIGINS }}"
'''

hooks.Filters.ENV_PATCHES.add_item(("openedx-lms-common-settings", _COMMON_SETTINGS))
hooks.Filters.ENV_PATCHES.add_item(("openedx-cms-common-settings", _COMMON_SETTINGS))
