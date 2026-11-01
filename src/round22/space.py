"""Three fixed R19 anchors: the complete canonical second-swap union."""
import hashlib
import itertools
from collections import Counter
from src.round13.common import fingerprint, require

DECLARED = 173499
B0 = 'c1fbd71e9dfca4e0a7d0d603d496fff8a71e2bc406d12eee113ab2bc4207b71d'
S = 'fa31ae444cd7afcf008b9d8d4d10a8ce6a8b8533c4d8f68c27bcf0003106d372'
ANCHORS = (
    ('q1', 1412, 1118, '34c4d7c5aca84316b12af6a06fd594754dc30f9bec5b8ddf3463b874a83b8ade'),
    ('q2', 2021, 1123, '3f89578074df99f7a3b7de27dcb9c26022364f852ee102b0648eae951e910d5f'),
    ('q3', 1941, 1200, '2b4b755f41d56ca39c3b39e2baa1acd44a64b03208611703dbbfb6c3865f4ef7'),
)
INTERMEDIATES = ANCHORS


def validate_pool(center, donors, states):
    require(len(center) == len(set(center)) == 28 and len(donors) == len(set(donors)) == 2143, 'R22_POOL_COUNT')
    require(not set(center) & set(donors) and sorted(center+donors) == list(range(2171)), 'R22_POOL_SET')
    require(len(set(states.values())) == 2171 and all(type(i) is int for i in center+donors), 'R22_STATES')
    require(fingerprint(sorted(states[i] for i in center)) == S, 'R22_CENTER_IDENTITY')
    require({r for _,r,_,_ in ANCHORS} <= set(center)
            and {a for _,_,a,_ in ANCHORS} | {1217,1284} <= set(donors), 'R22_MEMBERSHIP')


def families(remove, add):
    if (len(remove) != 2 or len(set(remove)) != 2 or len(add) != 2
            or len(set(add)) != 2 or set(remove) & set(add)):
        return []
    return [label for label,r,a,_ in ANCHORS if r in remove and a in add]


def operations(center, donors):
    """Pair order is numeric lexicographic; the same anchor couples R and A."""
    for remove in itertools.combinations(sorted(center), 2):
        active = [a for _,r,a,_ in ANCHORS if r in remove]
        if not active:
            continue
        additions = {tuple(sorted((a,b))) for a in active for b in donors if b != a}
        for add in sorted(additions):
            yield remove, add


def iter_candidates(center, donors, states, check=lambda: None):
    validate_pool(center, donors, states)
    center_set = set(center)
    for ordinal,(remove,add) in enumerate(operations(center, donors)):
        if ordinal % 512 == 0:
            check()
        indices = sorted((center_set-set(remove)) | set(add))
        members = families(remove, add)
        require(len(indices) == 28 and len(center_set ^ set(indices)) == 4 and members, 'R22_SECOND_SWAP')
        yield dict(ordinal=ordinal,remove=list(remove),add=list(add),indices=indices,
                   identity=fingerprint(sorted(states[i] for i in indices)),family_owner=members[0],families=members)


def summary(center, donors, states, check=lambda: None):
    identities,owners,deletions = set(),Counter(),Counter()
    order,operations_order = hashlib.sha256(),hashlib.sha256()
    first=last=None
    for row in iter_candidates(center, donors, states, check):
        require(row['identity'] not in identities,'R22_DUPLICATE_IDENTITY')
        identities.add(row['identity']);owners[row['family_owner']]+=1;deletions[tuple(row['remove'])]+=1
        order.update((row['identity']+'\n').encode())
        operations_order.update((','.join(map(str,row['remove']+row['add']))+'\n').encode())
        first=row if first is None else first;last=row
    require(len(identities)==DECLARED and dict(owners)==dict(q1=57834,q2=57833,q3=57832),'R22_EXACT_UNION')
    require(len(deletions)==78 and Counter(deletions.values())=={2142:75,4283:3},'R22_DELETION_PAIRS')
    return dict(status='PASS',declared_candidates=DECLARED,unique_identities=len(identities),owner_counts=dict(owners),
        family_sizes=[57834]*3,pairwise_intersections=[1,1,1],triple_intersection=0,intersection=3,
        identity_order_sha256=order.hexdigest(),pair_order_sha256=operations_order.hexdigest(),first=first,last=last,
        deletion_pair_counts={','.join(map(str,k)):v for k,v in deletions.items()},
        traversal='unordered remove pair numeric lexicographic, then unordered add pair numeric lexicographic',
        symmetric_difference_from_S=4,disjoint_from_R19_single_and_R21_third=True,
        history_filter_applied=False,candidate_REUSED=0,earlier_identity_disjointness_claimed=False)
