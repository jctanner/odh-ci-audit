from setuptools import setup, find_packages

setup(
    name="ci_audit",
    version="0.1.0",
    description="CI/CD test failure analysis for opendatahub-operator",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "click>=8.1.0",
        "PyGithub>=2.1.0",
        "sqlalchemy>=2.0.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
        "python-Levenshtein>=0.21.0",
        "tqdm>=4.66.0",
        "tabulate>=0.9.0",
        "colorama>=0.4.6",
    ],
    entry_points={
        "console_scripts": [
            "ci-audit-collect=ci_audit.cli:collect",
            "ci-audit-analyze=ci_audit.cli:analyze",
            "ci-audit-query=ci_audit.cli:query",
        ],
    },
)
