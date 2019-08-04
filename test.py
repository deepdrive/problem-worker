from worker import EvalWorker


def test_eval_worker():
    worker = EvalWorker()
    worker.loop(max_iters=1)


if __name__ == '__main__':
    test_eval_worker()
