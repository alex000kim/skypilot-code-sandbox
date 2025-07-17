"""
Simple benchmarking script for Modal Sandboxes.

Usage:
    python modal_benchmark.py
"""

import argparse
import asyncio
import sys
import time

import modal


class ModalBenchmark:
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.tests = [
            ("Basic Math", "print(2 + 2)"),
            ("Loop", "print(sum(range(100)))"),
            ("String Operations", "text = 'Hello World'; print(text.upper())"),
            ("List Comprehension", "squares = [x**2 for x in range(10)]; print(squares[:5])"),
            ("Import Module", "import math; print(math.pi)"),
        ]

    async def execute_code(self, code: str):
        start_time = time.time()
        
        try:
            app = modal.App.lookup(self.app_name, create_if_missing=True)
            sandbox = modal.Sandbox.create(
                app=app,
                image=modal.Image.debian_slim(),
                timeout=60
            )
            
            process = sandbox.exec("python", "-c", code)
            stdout = process.stdout.read()
            stderr = process.stderr.read()
            exit_code = process.wait()
            
            sandbox.terminate()
            
            return {
                "success": exit_code == 0,
                "response_time": time.time() - start_time,
                "output": stdout or "",
                "error": stderr or ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "response_time": time.time() - start_time,
                "error": str(e)
            }

    async def run_benchmark(self, iterations: int = 3):
        print(f"Running Modal benchmark ({iterations} iterations per test)\n")
        
        all_times = []
        successful = 0
        total = 0
        
        for test_name, code in self.tests:
            print(f"Testing: {test_name}")
            test_times = []
            
            for i in range(iterations):
                result = await self.execute_code(code)
                total += 1
                
                if result["success"]:
                    successful += 1
                    test_times.append(result["response_time"])
                    all_times.append(result["response_time"])
                    output = result["output"][:50] + "..." if len(result["output"]) > 50 else result["output"]
                    print(f"  ✓ {i+1}: {result['response_time']:.3f}s - {output.strip()}")
                else:
                    error = result.get('error', 'Unknown error')
                    error = error[:50] + "..." if len(error) > 50 else error
                    print(f"  ✗ {i+1}: {error}")
                
                await asyncio.sleep(0.5)
            
            if test_times:
                print(f"  Average: {sum(test_times)/len(test_times):.3f}s\n")
            else:
                print("  All failed\n")
        
        print("=" * 40)
        print("SUMMARY")
        print("=" * 40)
        print(f"Tests: {total}, Success: {successful} ({successful/total*100:.1f}%)")
        
        if all_times:
            avg = sum(all_times) / len(all_times)
            print(f"Average: {avg:.3f}s")
            print(f"Range: {min(all_times):.3f}s - {max(all_times):.3f}s")


def main():
    parser = argparse.ArgumentParser(description="Modal benchmark")
    parser.add_argument("--app-name", default="benchmark-app")
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    
    try:
        import modal
    except ImportError:
        print("Error: pip install modal")
        sys.exit(1)
    
    asyncio.run(ModalBenchmark(args.app_name).run_benchmark(args.iterations))


if __name__ == "__main__":
    main() 