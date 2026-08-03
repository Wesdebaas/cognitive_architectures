"""Epistemic error: how stale the robot's knowledge of an item is."""

# Seconds after an observation at which knowledge of an item is worthless.
# Placeholder values, NEED TUNING.
STALENESS_TIME = {
    'rubbish': 240.0,
    'roast': 400.0,
    'place_setting': 600.0,
    'juice': 900.0,
    'wine': 900.0,
    'spare_wine': 3600.0,  # long on purpose to keep tv_cabinet out of the ranking, also realistic because stock isn't changing as often
}

def epistemic_error(elapsed, staleness_time):
    """E = elapsed / staleness_time, clamped at 1. Never observed is elapsed=inf."""
    return min(1.0, elapsed / staleness_time)


if __name__ == '__main__':
    elapsed_times = [0, 25, 50, 100, 150, 300, 600]

    header = ' '.join(f'{t:>6}s' for t in elapsed_times)
    print(f'{"item":<14}{"T":>7}   {header}')

    for item, staleness in sorted(STALENESS_TIME.items(), key=lambda kv: kv[1]):
        row = ' '.join(f'{epistemic_error(t, staleness):>7.3f}' for t in elapsed_times)
        print(f'{item:<14}{staleness:>6.0f}s  {row}')

    print(f'\nnever observed -> E = {epistemic_error(float("inf"), 400.0):.3f}')
