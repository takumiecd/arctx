"""arctx CLI guide command."""

import argparse


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "guide",
        help="Print the arctx usage guide and concepts",
    )
    return parser


def cli_guide(args) -> int:
    guide_text = """\
# arctx Guide

arctx is a tool for recording optimization and problem-solving processes.

## Core Concepts

*   **Node & Step**:
    These form the Directed Acyclic Graph (DAG) that records the history of the process.
    - `Node` represents a state or a point in time.
    - `Step` represents a transition, connecting input Nodes to an output Node.

*   **Payload**:
    Payloads give meaning to Nodes and Steps. They are attached to records to hold domain-specific data.
    Extensions customize arctx by defining new payload types and altering their fields. Since there are
    multiple types of payloads, you should choose and use them appropriately for your task.

*   **Lane**:
    When tackling a large or complex problem, visualizing the entire massive graph becomes difficult.
    Lanes exist to break down the problem into smaller, manageable pieces. You can think of a lane as
    a container or a workspace that allows you to advance your problem-solving step by step in isolation.
"""
    print(guide_text)
    return 0
