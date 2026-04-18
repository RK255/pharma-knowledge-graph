#!/usr/bin/env python3
"""
Progress Module
===============
Handles progress reporting for the pipeline. 
Matches the interface expected by dailymed_pipeline.py.
"""

class Progress:
    def __init__(self, step_num=1, step_name="Task", total=0, description=""):
        self.step_num = step_num
        self.step_name = step_name
        self.total = total
        self.description = description
        self.current = 0

    def update(self, amount=1, description=None):
        self.current += amount
        if description:
            self.description = description
        self._print_status()

    def report(self, percent, message):
        """Report progress based on percentage and message."""
        msg = f"[Step {self.step_num}: {self.step_name}] {message} ({percent*100:.0f}%)"
        print(msg)

    def _print_status(self):
        msg = f"[Step {self.step_num}: {self.step_name}] "
        if self.description:
            msg += f"{self.description} - "
        msg += f"{self.current} items processed"
        print(msg, end='\r')

    def complete(self, message=""):
        print(f"\n[Step {self.step_num}: {self.step_name}] {message}")
