"""
Simple benchmarking script for the Python code execution API.

Usage:
    python simple_benchmark.py --host http://localhost:8080 --token YOUR_AUTH_TOKEN
"""

import argparse
import asyncio
import os
import sys
import time

import httpx


class SimpleBenchmark:
    def __init__(self, base_url: str, auth_token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {"Authorization": f"Bearer {auth_token}"}
        self.tests = [
            ("Basic Math", "print(2 + 2)"),
            ("Loop", "print(sum(range(100)))"),
            ("String Operations", "text = 'Hello World'; print(text.upper())"),
            ("List Comprehension", "squares = [x**2 for x in range(10)]; print(squares[:5])"),
            ("Import Module", "import math; print(math.pi)"),
        ]

    async def health_check(self):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", headers=self.headers, timeout=10)
                return response.status_code == 200
        except:
            return False

    async def execute_code(self, code: str):
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/execute",
                    json={"code": code, "language": "python"},
                    headers=self.headers,
                    timeout=30
                )
                
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": data.get("success", False),
                        "response_time": response_time,
                        "output": data.get("stdout", ""),
                        "error": data.get("stderr", "")
                    }
                else:
                    return {
                        "success": False,
                        "response_time": response_time,
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "success": False,
                "response_time": time.time() - start_time,
                "error": str(e)
            }

    async def run_benchmark(self, iterations=3):
        print(f"Running API benchmark ({iterations} iterations per test)\n")
        
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
                    print(f"  ✓ {i+1}: {result['response_time']:.3f}s")
                else:
                    print(f"  ✗ {i+1}: {result.get('error', 'Unknown error')}")
                
                await asyncio.sleep(0.1)
            
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
    parser = argparse.ArgumentParser(description="API benchmark")
    parser.add_argument("--host", default="http://localhost:8080")
    parser.add_argument("--token", help="Auth token")
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    
    auth_token = args.token or os.getenv("AUTH_TOKEN")
    if not auth_token:
        print("Error: Need auth token via --token or AUTH_TOKEN env var")
        sys.exit(1)
    
    benchmark = SimpleBenchmark(args.host, auth_token)
    
    async def run():
        print("Checking API health...")
        if not await benchmark.health_check():
            print("Error: API health check failed")
            sys.exit(1)
        print("✓ API healthy\n")
        await benchmark.run_benchmark(args.iterations)
    
    asyncio.run(run())


if __name__ == "__main__":
    main() 