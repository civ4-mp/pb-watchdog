from setuptools import find_packages, setup

setup(
    name="civ4-mp.pb-watchdog",
    version="2.0.1",
    author="Olaf S., Zulan",
    python_requires=">=3.7",
    packages=find_packages(),
    scripts=["bin/civpb-confirm-popup", "bin/civpb-kill"],
    entry_points="""
      [console_scripts]
      civpb-watchdog=civpb_watchdog:main
      """,
    install_requires=[
        "click",
        "click-config-file",
        "click_log",
        "prometheus_client",
        "setuptools",
        "scapy",
        "toml",
    ],
)
