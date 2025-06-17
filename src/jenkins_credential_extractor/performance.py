# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Performance benchmarking and monitoring for Jenkins automation."""

import time
import statistics
import json
import csv
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""

    operation: str
    total_items: int
    successful_items: int
    failed_items: int
    total_duration: float
    average_duration_per_item: float
    min_duration: float
    max_duration: float
    median_duration: float
    throughput_per_second: float
    error_rate: float
    timestamp: str
    method_used: str
    thread_count: Optional[int] = None
    batch_size: Optional[int] = None


@dataclass
class PerformanceMetrics:
    """Individual operation performance metrics."""

    duration: float
    success: bool
    error_message: Optional[str] = None
    retry_count: int = 0
    thread_id: Optional[str] = None


class PerformanceBenchmark:
    """Performance benchmarking system for Jenkins automation."""

    def __init__(self, results_dir: Optional[Path] = None):
        """Initialize benchmark system."""
        self.results_dir = (
            results_dir or Path.home() / ".jenkins_extractor" / "benchmarks"
        )
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.current_metrics: List[PerformanceMetrics] = []
        self.operation_name = ""
        self.start_time = 0.0
        self.method_used = ""
        self.thread_count: Optional[int] = None
        self.batch_size: Optional[int] = None

    def start_benchmark(
        self,
        operation: str,
        method: str,
        thread_count: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        """Start a new benchmark run."""
        self.operation_name = operation
        self.method_used = method
        self.thread_count = thread_count
        self.batch_size = batch_size
        self.current_metrics.clear()
        self.start_time = time.time()

        console.print(f"[blue]📊 Starting benchmark: {operation} ({method})[/blue]")
        if thread_count:
            console.print(f"[blue]  Threads: {thread_count}[/blue]")
        if batch_size:
            console.print(f"[blue]  Batch size: {batch_size}[/blue]")

    def record_operation(
        self,
        duration: float,
        success: bool,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        thread_id: Optional[str] = None,
    ) -> None:
        """Record metrics for a single operation."""
        metric = PerformanceMetrics(
            duration=duration,
            success=success,
            error_message=error_message,
            retry_count=retry_count,
            thread_id=thread_id,
        )
        self.current_metrics.append(metric)

    def finish_benchmark(self) -> BenchmarkResult:
        """Finish benchmark and calculate results."""
        total_duration = time.time() - self.start_time
        total_items = len(self.current_metrics)
        successful_items = sum(1 for m in self.current_metrics if m.success)
        failed_items = total_items - successful_items

        if not self.current_metrics:
            # Handle edge case of no operations
            return BenchmarkResult(
                operation=self.operation_name,
                total_items=0,
                successful_items=0,
                failed_items=0,
                total_duration=total_duration,
                average_duration_per_item=0.0,
                min_duration=0.0,
                max_duration=0.0,
                median_duration=0.0,
                throughput_per_second=0.0,
                error_rate=0.0,
                timestamp=datetime.now().isoformat(),
                method_used=self.method_used,
                thread_count=self.thread_count,
                batch_size=self.batch_size,
            )

        durations = [m.duration for m in self.current_metrics]
        average_duration = statistics.mean(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        median_duration = statistics.median(durations)
        throughput = successful_items / total_duration if total_duration > 0 else 0
        error_rate = (failed_items / total_items) * 100 if total_items > 0 else 0

        result = BenchmarkResult(
            operation=self.operation_name,
            total_items=total_items,
            successful_items=successful_items,
            failed_items=failed_items,
            total_duration=total_duration,
            average_duration_per_item=average_duration,
            min_duration=min_duration,
            max_duration=max_duration,
            median_duration=median_duration,
            throughput_per_second=throughput,
            error_rate=error_rate,
            timestamp=datetime.now().isoformat(),
            method_used=self.method_used,
            thread_count=self.thread_count,
            batch_size=self.batch_size,
        )

        self._save_result(result)
        self._display_result(result)

        return result

    def _save_result(self, result: BenchmarkResult) -> None:
        """Save benchmark result to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{result.operation}_{result.method_used}_{timestamp}.json"
        filepath = self.results_dir / filename

        with open(filepath, "w") as f:
            json.dump(asdict(result), f, indent=2)

        console.print(f"[green]💾 Benchmark results saved to {filepath}[/green]")

    def _display_result(self, result: BenchmarkResult) -> None:
        """Display benchmark results in a formatted table."""
        table = Table(title=f"Benchmark Results: {result.operation}")

        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_column("Unit", style="green")

        table.add_row("Method", result.method_used, "")
        table.add_row("Total Items", str(result.total_items), "items")
        table.add_row("Successful", str(result.successful_items), "items")
        table.add_row("Failed", str(result.failed_items), "items")
        table.add_row("Total Duration", f"{result.total_duration:.2f}", "seconds")
        table.add_row(
            "Avg Duration/Item", f"{result.average_duration_per_item:.3f}", "seconds"
        )
        table.add_row("Throughput", f"{result.throughput_per_second:.2f}", "items/sec")
        table.add_row("Error Rate", f"{result.error_rate:.1f}", "%")

        if result.thread_count:
            table.add_row("Thread Count", str(result.thread_count), "threads")

        console.print(table)

        # Performance assessment
        self._assess_performance(result)

    def _assess_performance(self, result: BenchmarkResult) -> None:
        """Assess performance and provide recommendations."""
        console.print("\n[bold blue]Performance Assessment:[/bold blue]")

        # Throughput assessment
        if result.throughput_per_second >= 5.0:
            console.print("[green]✓ Excellent throughput (≥5 items/sec)[/green]")
        elif result.throughput_per_second >= 2.0:
            console.print("[yellow]⚠ Good throughput (≥2 items/sec)[/yellow]")
        else:
            console.print(
                "[red]⚠ Low throughput (<2 items/sec) - consider optimization[/red]"
            )

        # Error rate assessment
        if result.error_rate == 0:
            console.print("[green]✓ Perfect reliability (0% error rate)[/green]")
        elif result.error_rate <= 5:
            console.print("[yellow]⚠ Good reliability (≤5% error rate)[/yellow]")
        else:
            console.print("[red]⚠ High error rate (>5%) - investigate failures[/red]")

        # Method recommendations
        if result.total_items >= 50 and result.method_used == "sequential":
            console.print(
                "[yellow]💡 Consider using parallel processing for better performance[/yellow]"
            )
        elif result.total_items >= 100 and result.method_used == "parallel":
            console.print(
                "[yellow]💡 Consider using optimized batch processing[/yellow]"
            )

    def compare_methods(self, operation: str, limit: int = 5) -> None:
        """Compare performance across different methods for an operation."""
        results = self.load_recent_results(operation, limit)

        if len(results) < 2:
            console.print("[yellow]Need at least 2 results to compare methods[/yellow]")
            return

        table = Table(title=f"Method Comparison: {operation}")
        table.add_column("Method", style="cyan")
        table.add_column("Items", style="blue")
        table.add_column("Duration", style="green")
        table.add_column("Throughput", style="magenta")
        table.add_column("Error Rate", style="red")
        table.add_column("Date", style="yellow")

        for result in results:
            table.add_row(
                result.method_used,
                str(result.total_items),
                f"{result.total_duration:.1f}s",
                f"{result.throughput_per_second:.2f}/s",
                f"{result.error_rate:.1f}%",
                result.timestamp[:10],  # Just the date
            )

        console.print(table)

        # Find best performing method
        best_throughput = max(results, key=lambda r: r.throughput_per_second)
        best_reliability = min(results, key=lambda r: r.error_rate)

        console.print(
            f"\n[green]🏆 Best throughput: {best_throughput.method_used} "
            f"({best_throughput.throughput_per_second:.2f} items/sec)[/green]"
        )
        console.print(
            f"[green]🛡️ Best reliability: {best_reliability.method_used} "
            f"({best_reliability.error_rate:.1f}% error rate)[/green]"
        )

    def load_recent_results(
        self, operation: str, limit: int = 10
    ) -> List[BenchmarkResult]:
        """Load recent benchmark results for an operation."""
        results = []
        pattern = f"{operation}_*.json"

        matching_files = sorted(
            self.results_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        for filepath in matching_files:
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    result = BenchmarkResult(**data)
                    results.append(result)
            except Exception as e:
                console.print(f"[red]Error loading {filepath}: {e}[/red]")

        return results

    def generate_csv_report(
        self, operation: str, output_file: Optional[Path] = None
    ) -> Path:
        """Generate CSV report of all results for an operation."""
        results = self.load_recent_results(operation, limit=100)

        if not results:
            raise ValueError(f"No results found for operation: {operation}")

        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.results_dir / f"{operation}_report_{timestamp}.csv"

        with open(output_file, "w", newline="") as csvfile:
            fieldnames = [
                "timestamp",
                "method_used",
                "total_items",
                "successful_items",
                "failed_items",
                "total_duration",
                "average_duration_per_item",
                "throughput_per_second",
                "error_rate",
                "thread_count",
                "batch_size",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "timestamp": result.timestamp,
                        "method_used": result.method_used,
                        "total_items": result.total_items,
                        "successful_items": result.successful_items,
                        "failed_items": result.failed_items,
                        "total_duration": result.total_duration,
                        "average_duration_per_item": result.average_duration_per_item,
                        "throughput_per_second": result.throughput_per_second,
                        "error_rate": result.error_rate,
                        "thread_count": result.thread_count,
                        "batch_size": result.batch_size,
                    }
                )

        console.print(f"[green]📊 CSV report generated: {output_file}[/green]")
        return output_file


class PerformanceTracker:
    """Context manager for tracking individual operation performance."""

    def __init__(
        self, benchmark: PerformanceBenchmark, thread_id: Optional[str] = None
    ):
        self.benchmark = benchmark
        self.thread_id = thread_id
        self.start_time = 0.0
        self.retry_count = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        success = exc_type is None
        error_message = str(exc_val) if exc_val else None

        self.benchmark.record_operation(
            duration=duration,
            success=success,
            error_message=error_message,
            retry_count=self.retry_count,
            thread_id=self.thread_id,
        )

    def increment_retry(self):
        """Increment retry count for this operation."""
        self.retry_count += 1


def benchmark_automation_methods(
    automation,
    test_credentials: List[tuple],
    methods_to_test: Optional[List[str]] = None,
) -> Dict[str, BenchmarkResult]:
    """Benchmark different automation methods with the same dataset."""
    if methods_to_test is None:
        methods_to_test = ["sequential", "parallel", "optimized"]

    benchmark = PerformanceBenchmark()
    results = {}

    for method in methods_to_test:
        console.print(f"\n[bold blue]Testing method: {method}[/bold blue]")

        # Determine parameters based on method
        if method == "sequential":
            thread_count = 1
        elif method == "parallel":
            thread_count = min(10, len(test_credentials))
        else:  # optimized
            thread_count = None  # Uses single script

        try:
            benchmark.start_benchmark(
                operation="password_decryption",
                method=method,
                thread_count=thread_count,
                batch_size=len(test_credentials),
            )

            # Execute based on method
            if method == "sequential":
                for username, encrypted_pass in test_credentials:
                    with PerformanceTracker(benchmark):
                        try:
                            automation._decrypt_password_with_retry(encrypted_pass)
                        except Exception:
                            pass  # Error recorded by tracker

            elif method == "parallel":
                automation.batch_decrypt_passwords_parallel(test_credentials)

            elif method == "optimized":
                automation.batch_decrypt_passwords_optimized(test_credentials)

            result = benchmark.finish_benchmark()
            results[method] = result

        except Exception as e:
            console.print(f"[red]Failed to benchmark {method}: {e}[/red]")

    return results


# Global benchmark instance
global_benchmark = PerformanceBenchmark()
