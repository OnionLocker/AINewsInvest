# -*- coding: utf-8 -*-
"""Tests for pipeline agents module — synthesis and filtering logic.

Note: In v7, the tech bypass mechanism was removed. NewsSkill and TechSkill
now run in parallel on all candidates. The news safety checks are handled
by the synthesis layer (contradiction filter, confidence penalty, etc.).

These tests verify that the synthesis layer correctly handles negative news.
"""
from __future__ import annotations

import pytest

# v7: _check_tech_bypass and run_news_filter were removed.
# The safety logic now lives in synthesize_agent_results via:
# - contradiction filter (buy + avoid = skip)
# - confidence penalty for missing signals
# - insider selling penalty
# These are covered by the existing test_scorers.py and integration tests.
