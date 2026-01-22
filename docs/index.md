# CI Audit Documentation

This documentation covers the CI audit system for analyzing test failures in the [opendatahub-io/opendatahub-operator](https://github.com/opendatahub-io/opendatahub-operator) repository.

## What is This?

A Python-based data collection and analysis system that:

- Scrapes PR metadata from GitHub API
- Downloads Prow CI test artifacts from GCS
- Parses JUnit XML test results and build logs
- Stores structured data in PostgreSQL
- Provides REST API and web frontend for browsing test results
- Analyzes failure patterns and trends

## Target Audience

Developers and SREs working on:

- OpenShift/Kubernetes operators
- CI/CD pipelines using Prow
- E2E test frameworks (Ginkgo/Gomega)
- Test reliability and flake reduction

## Documentation Structure

**Setup**: Installation, configuration, and deployment of the audit system

**Prow CI & Testing**: Understanding the Prow CI architecture and test framework

**Analysis**: Data analysis of test duration and failure patterns

**Findings**: Results from analyzing the collected data

**Debugging & Remediation**: Active work to implement fail-fast diagnostics and reduce test failures

**Recommendations**: Proposed improvements to test reliability and CI infrastructure

**Code Reference**: SQL queries and Python scripts used for analysis

**API Reference**: Code documentation for the audit system modules

## Quick Links

- [Installation](setup/installation.md) - Get started with local or PostgreSQL deployment
- [Prow Architecture](prow/architecture.md) - Understand how Prow CI works
- [Prow JSON API](prow/api.md) - Efficient test run discovery using Prow's API
- [Database Schema](setup/database-schema.md) - Schema reference for queries
- [SQL Query Library](code/queries.md) - Reusable SQL queries for analysis
- [Debugging & Remediation](debugging/index.md) - Active fail-fast diagnostic development

## Data Sources

**GitHub**: Pull request metadata, comments, reviews

**Prow/GCS**: Test run artifacts (JUnit XML, build logs, Prow metadata)

**Time Period**: July 2025 - January 2026 (6 months, 895 PRs, 5,166 test runs)

## Technology Stack

- **Python 3.9+**: Data collection and analysis
- **SQLAlchemy**: Database ORM with PostgreSQL
- **PostgreSQL**: Data storage with JSONB for flexible JSON
- **Flask**: REST API for querying test data
- **Vanilla JavaScript**: Frontend web interface
- **MkDocs + Material**: Documentation
- **Prow CI**: OpenShift test infrastructure
- **Ginkgo/Gomega**: Go test framework used by operator
