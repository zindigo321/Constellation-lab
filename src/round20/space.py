"""Canonical unordered deletion/addition pairs for exactly three fixed families."""
import hashlib
from collections import Counter
from itertools import combinations
from src.round13.common import fingerprint, require

DECLARED = 173473
ANCHORS = (('q1', 911, 214), ('q2', 676, 1440), ('q3', 911, 2126))
B0 = 'c1fbd71e9dfca4e0a7d0d603d496fff8a71e2bc406d12eee113ab2bc4207b71d'
S = 'fa31ae444cd7afcf008b9d8d4d10a8ce6a8b8533c4d8f68c27bcf0003106d372'

def validate_pool(center, donors, states):
    require(len(center)==len(set(center))==28 and len(donors)==len(set(donors))==2143, 'R20_POOL_COUNT')
    require(not set(center)&set(donors) and sorted(center+donors)==list(range(2171)), 'R20_POOL_SET')
    require(len(set(states.values()))==2171 and all(type(i) is int for i in center+donors), 'R20_STATES')
    require(fingerprint(sorted(states[i] for i in center))==S, 'R20_CENTER_IDENTITY')
    require({1217,1284}<=set(donors) and {2021,2023}<=set(center), 'R20_DONOR_MEMBERSHIP')

def families(remove, add):
    return [q for q,r,a in ANCHORS if r in remove and a in add]

def operations(center, donors):
    for remove in combinations(sorted(center),2):
        active={a for _,r,a in ANCHORS if r in remove}
        additions={tuple(sorted((a,b))) for a in active for b in donors if a!=b}
        for add in sorted(additions):
            yield remove,add

def iter_candidates(center, donors, states, check=lambda:None):
    validate_pool(center,donors,states)
    for ordinal,(remove,add) in enumerate(operations(center,donors)):
        if ordinal%512==0:check()
        indices=sorted((set(center)-set(remove))|set(add))
        memberships=families(remove,add)
        yield dict(ordinal=ordinal,remove=list(remove),add=list(add),indices=indices,
            identity=fingerprint(sorted(states[i] for i in indices)),family_owner=memberships[0],families=memberships)

def summary(center, donors, states, check=lambda:None):
    ids=set(); owners=Counter(); deletions=Counter(); order=hashlib.sha256(); pairs=hashlib.sha256()
    first=last=None
    for row in iter_candidates(center,donors,states,check):
        require(row['identity'] not in ids,'R20_DUPLICATE_IDENTITY');ids.add(row['identity'])
        owners[row['family_owner']]+=1;deletions[tuple(row['remove'])]+=1
        order.update((row['identity']+'\n').encode())
        pairs.update((','.join(map(str,row['remove']+row['add']))+'\n').encode())
        first=row if first is None else first;last=row
    require(len(ids)==DECLARED and dict(owners)==dict(q1=57834,q2=57833,q3=57806),'R20_EXACT_UNION')
    require(Counter(deletions.values())==Counter({4283:26,2142:26,6423:1}),'R20_COMBINATORIAL_DECOMPOSITION')
    return dict(status='PASS',declared_candidates=len(ids),unique_identities=len(ids),owner_counts=dict(owners),
        identity_order_sha256=order.hexdigest(),pair_order_sha256=pairs.hexdigest(),first=first,last=last,
        deletion_pair_counts={','.join(map(str,k)):v for k,v in deletions.items()},
        traversal='numeric lexicographic unordered removal pair, then unordered addition pair')
