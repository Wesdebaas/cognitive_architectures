"""Epistemic error: how stale the robot's knowledge of an item is."""


def epistemic_error(elapsed, staleness_time):
    """E = elapsed / staleness_time, clamped at 1. Never observed is elapsed=inf."""
    return min(1.0, elapsed / staleness_time)


if __name__ == '__main__':
    from goal_awareness_scenario.params import load

    staleness_time = load()['staleness_time']
    elapsed_times = [0, 25, 50, 100, 150, 300, 600]

    header = ' '.join(f'{t:>6}s' for t in elapsed_times)
    print(f'{"item":<14}{"T":>7}   {header}')

    for item, staleness in sorted(staleness_time.items(), key=lambda kv: kv[1]):
        row = ' '.join(f'{epistemic_error(t, staleness):>7.3f}' for t in elapsed_times)
        print(f'{item:<14}{staleness:>6.0f}s  {row}')

    print(f'\nnever observed -> E = {epistemic_error(float("inf"), 400.0):.3f}')
