"""PC1 Ubuntu VM의 제한된 CPU 부하 시연. 시스템 종료는 수행하지 않는다."""

import argparse
import multiprocessing as mp
import os
import signal
import socket
import time


def worker(stop, deadline, duty):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    value = 1
    while not stop.is_set() and time.monotonic() < deadline:
        started = time.monotonic()
        busy_until = min(started + 0.1 * duty, deadline)
        while time.monotonic() < busy_until:
            value = (value * 1664525 + 1013904223) & 0xFFFFFFFF
        stop.wait(max(0.0, min(started + 0.1, deadline) - time.monotonic()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=90)
    parser.add_argument('--load', type=int, default=60,
                        help='각 작업 프로세스의 목표 CPU 사용 비율: 10~70')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120 or not 10 <= args.load <= 70:
        parser.error('실행 시간은 1~120초, 부하는 10~70으로 지정하세요.')
    if os.name != 'posix' or socket.gethostname().split('.')[0] != 'pc1-k3s':
        parser.error('PC1 Ubuntu VM인 pc1-k3s에서 실행하세요.')

    available = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)
    count = min(available, 2)
    stop = mp.Event()
    children = []
    deadline = time.monotonic() + args.seconds

    def request_stop(signum, frame):
        stop.set()

    previous = {sig: signal.signal(sig, request_stop)
                for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        print(f'CPU 부하 시작: 작업 {count}개, 목표 {args.load}%, 최대 {args.seconds}초', flush=True)
        print('Ctrl+C로 중단할 수 있습니다. 시스템은 자동 종료하지 않습니다.', flush=True)
        for _ in range(count):
            child = mp.Process(target=worker, args=(stop, deadline, args.load / 100))
            child.daemon = True
            child.start()
            children.append(child)
        while time.monotonic() < deadline and not stop.wait(0.2):
            if any(child.exitcode not in (None, 0) for child in children):
                raise RuntimeError('부하 작업 프로세스가 비정상 종료됐습니다.')
    finally:
        stop.set()
        for child in children:
            child.join(timeout=2)
            if child.is_alive():
                child.terminate()
                child.join(timeout=2)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        print('CPU 부하 종료', flush=True)


if __name__ == '__main__':
    main()
