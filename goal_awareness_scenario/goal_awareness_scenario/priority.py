"""Priority P = E x A, aggregated per station."""

from attention import CN, attention, distances, load_edges, load_storage, name
from epistemic import STALENESS_TIME, epistemic_error

def priority(attention_by_item, error_by_item, storage):
    """P(station) = sum of E(item) * A(item) over the items kept there."""
    return {
        station: sum(error_by_item[i] * attention_by_item.get(i, 0.0) for i in items)
        for station, items in storage.items()
    }


if __name__ == '__main__':
    alpha = 0.3

    # Demo for the KB query: seconds since each item was last observed, inf meaning never. 
    last_seen = {
        'roast': 20.0,
        'place_setting': 50.0,
        'rubbish': 70.0,
        'juice': float('inf'),
        'wine': float('inf'),
        'spare_wine': float('inf'),
    }

    edges = load_edges()
    storage = load_storage()

    E = {item: epistemic_error(t, STALENESS_TIME[item]) for item, t in last_seen.items()}

    print('E, from last_seen:')
    for item, e in sorted(E.items()):
        print(f'  {item:<14} {e:.3f}')

    for goal in ['prepare_dinner', 'serve_guests']:
        A = {name(n): a for n, a in attention(distances(edges, CN[goal]), alpha).items()}
        P = priority(A, E, storage)

        print(f'\n{goal}   (alpha = {alpha})')
        for station, p in sorted(P.items(), key=lambda kv: -kv[1]):
            terms = ' + '.join(
                f'{i} {E[i]:.3f}x{A.get(i, 0.0):.3f}' for i in storage[station]
            )
            print(f'  P={p:.3f}  {station:<16}  {terms}')
