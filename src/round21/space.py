"""The complete limited third-swap union, ordered by r then unordered (a,b)."""
import hashlib
from collections import Counter
from src.round13.common import fingerprint, require

DECLARED = 111306
B0 = 'c1fbd71e9dfca4e0a7d0d603d496fff8a71e2bc406d12eee113ab2bc4207b71d'
S = 'fa31ae444cd7afcf008b9d8d4d10a8ce6a8b8533c4d8f68c27bcf0003106d372'
INTERMEDIATES = (('F1', 218, 'c3d734bf2f537c385056ee9fae7ca17948489ef6403680fc24b2c81623e3e6a9'),
                 ('F2', 1876, '9e2988a05547a0e4ffdd0d4d405aa4a1a7d47f31543b74ea3148ef602ad1cbb4'))
FIXED_REMOVED = frozenset({676, 2021})
FIXED_DONOR = 1440
SPECIAL = frozenset({218, 1876})


def validate_pool(center, donors, states):
    require(len(center) == len(set(center)) == 28 and len(donors) == len(set(donors)) == 2143, 'R21_POOL_COUNT')
    require(not set(center) & set(donors) and sorted(center+donors) == list(range(2171)), 'R21_POOL_SET')
    require(len(set(states.values())) == 2171 and all(type(i) is int for i in center+donors), 'R21_STATES')
    require(fingerprint(sorted(states[i] for i in center)) == S, 'R21_CENTER_IDENTITY')
    require(FIXED_REMOVED <= set(center) and {1217, 1284, 1440, 218, 1876} <= set(donors), 'R21_MEMBERSHIP')


def families(remove, add):
    if (len(remove) != 3 or len(set(remove)) != 3 or not FIXED_REMOVED <= set(remove)
            or len(add) != 3 or len(set(add)) != 3 or FIXED_DONOR not in add
            or set(remove) & set(add)):
        return []
    return [label for label, donor in [('G1', 218), ('G2', 1876)] if donor in add]


def operations(center, donors):
    removable = sorted(set(center)-FIXED_REMOVED)
    variable = sorted(set(donors)-{FIXED_DONOR})
    pairs = sorted({tuple(sorted((special, other))) for special in SPECIAL for other in variable if other != special})
    for r in removable:
        for pair in pairs:
            yield tuple(sorted((676, 2021, r))), tuple(sorted((FIXED_DONOR, *pair)))


def iter_candidates(center, donors, states, check=lambda: None):
    validate_pool(center, donors, states)
    center_set = set(center)
    for ordinal, (remove, add) in enumerate(operations(center, donors)):
        if ordinal % 512 == 0:
            check()
        indices = sorted((center_set-set(remove)) | set(add))
        memberships = families(remove, add)
        require(len(indices) == 28 and len(center_set ^ set(indices)) == 6 and bool(memberships), 'R21_THREE_SWAP')
        yield dict(ordinal=ordinal, remove=list(remove), add=list(add), indices=indices,
                   identity=fingerprint(sorted(states[i] for i in indices)),
                   family_owner=memberships[0], families=memberships)


def summary(center, donors, states, check=lambda: None):
    identities, owners, deletions = set(), Counter(), Counter()
    order, operation_order = hashlib.sha256(), hashlib.sha256()
    first = last = None
    for row in iter_candidates(center, donors, states, check):
        require(row['identity'] not in identities, 'R21_DUPLICATE_IDENTITY')
        identities.add(row['identity'])
        owners[row['family_owner']] += 1
        deletions[tuple(row['remove'])] += 1
        order.update((row['identity']+'\n').encode())
        operation_order.update((','.join(map(str, row['remove']+row['add']))+'\n').encode())
        first = row if first is None else first
        last = row
    require(len(identities) == DECLARED and dict(owners) == dict(G1=55666, G2=55640), 'R21_EXACT_UNION')
    require(len(deletions) == 26 and set(deletions.values()) == {4281}, 'R21_PER_R_COUNT')
    return dict(status='PASS', declared_candidates=DECLARED, unique_identities=len(identities),
                owner_counts=dict(owners), family_sizes=[55666, 55666], intersection=26,
                identity_order_sha256=order.hexdigest(), pair_order_sha256=operation_order.hexdigest(),
                first=first, last=last, deletion_triple_counts={','.join(map(str, k)): v for k, v in deletions.items()},
                traversal='r ascending, then numeric lexicographic unordered (a,b); C=(S-{676,2021,r})|{1440,a,b}',
                symmetric_difference_from_S=6, disjoint_from_R19_single_and_R20_double=True,
                earlier_different_center_identity_disjointness_claimed=False)
