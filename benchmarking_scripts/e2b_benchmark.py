"""
Simple benchmarking script for the E2B code interpreter API.

Usage:
    python e2b_benchmark.py --token YOUR_E2B_API_TOKEN --iterations 3
    
Or set E2B_API_KEY environment variable and run:
    python e2b_benchmark.py
"""

import argparse
import asyncio
import os
import sys
import time

from e2b_code_interpreter import Sandbox


class E2BBenchmark:
    def __init__(self, api_key: str):
        self.api_key = api_key
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
            sandbox = Sandbox(api_key=self.api_key, timeout=30)
            result = sandbox.run_code(code)
            response_time = time.time() - start_time
            
            return {
                "success": result.error is None,
                "response_time": response_time,
                "output": "\n".join(result.logs.stdout) if result.logs.stdout else "",
                "error": "\n".join(result.logs.stderr) if result.logs.stderr else (str(result.error) if result.error else "")
            }
        except Exception as e:
            return {
                "success": False,
                "response_time": time.time() - start_time,
                "error": str(e)
            }
        finally:
            try:
                sandbox.close()
            except:
                pass

    async def run_benchmark(self, iterations: int = 3):
        print(f"Running E2B benchmark ({iterations} iterations per test)\n")
        
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
    parser = argparse.ArgumentParser(description="E2B benchmark")
    parser.add_argument("--token", help="E2B API token")
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    
    api_key = args.token or os.getenv("E2B_API_KEY")
    if not api_key:
        print("Error: Need E2B API key via --token or E2B_API_KEY env var")
        sys.exit(1)
    
    try:
        from e2b_code_interpreter import Sandbox
    except ImportError:
        print("Error: pip install e2b-code-interpreter")
        sys.exit(1)
    
    asyncio.run(E2BBenchmark(api_key).run_benchmark(args.iterations))


if __name__ == "__main__":
    main()