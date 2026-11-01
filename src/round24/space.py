"""The complete, matched-anchor union of the three declared third-swap families."""
import hashlib
import itertools
from collections import Counter
from src.round13.common import fingerprint, require

DECLARED = 166970
B0 = 'c1fbd71e9dfca4e0a7d0d603d496fff8a71e2bc406d12eee113ab2bc4207b71d'
S = 'fa31ae444cd7afcf008b9d8d4d10a8ce6a8b8533c4d8f68c27bcf0003106d372'
ANCHORS = (
    ('p1', (676,1412), (196,1118), '5bb95ed489a6e33279912f3c9660a45515df921862c233294a8e25660e156341'),
    ('p2', (1412,1941), (2,1118), '176e6e11349809ee98cebcc60ec71975609be46e0409bda3cb691b303ae35130'),
    ('p3', (1412,1941), (640,1118), '824e842464e8ae793c4daf7e13e8b964549d891bef04233b2b1f4f8ba787b8b5'),
)
INTERMEDIATES = ANCHORS


def validate_pool(center, donors, states):
    require(len(center)==len(set(center))==28 and len(donors)==len(set(donors))==2143,'R24_POOL_COUNT')
    require(not set(center)&set(donors) and sorted(center+donors)==list(range(2171)),'R24_POOL_SET')
    require(len(states)==len(set(states.values()))==2171 and all(type(i) is int for i in center+donors),'R24_STATES')
    require(fingerprint(sorted(states[i] for i in center))==S,'R24_CENTER_IDENTITY')
    require(all(set(r)<=set(center) and set(a)<=set(donors) for _,r,a,_ in ANCHORS),'R24_ANCHOR_MEMBERSHIP')


def families(remove, add):
    if (len(remove)!=len(set(remove)) or len(remove)!=3 or len(add)!=len(set(add))
            or len(add)!=3 or set(remove)&set(add)):
        return []
    return [label for label,r,a,_ in ANCHORS if set(r)<set(remove) and set(a)<set(add)]


def effective_removals(center):
    """Only operation types: no new candidate identity is generated here."""
    return [r for r in itertools.combinations(sorted(center),3)
            if any(set(anchor_r)<set(r) for _,anchor_r,_,_ in ANCHORS)]


def operations(center, donors):
    for remove in effective_removals(center):
        active = [a for _,r,a,_ in ANCHORS if set(r)<set(remove)]
        additions = {tuple(sorted((*a,b))) for a in active for b in donors if b not in a}
        for add in sorted(additions):
            yield remove,add


def iter_candidates(center, donors, states, check=lambda:None):
    validate_pool(center,donors,states)
    original=set(center)
    for ordinal,(remove,add) in enumerate(operations(center,donors)):
        if ordinal%512==0:check()
        ids=sorted((original-set(remove))|set(add));members=families(remove,add)
        require(len(ids)==28 and len(original^set(ids))==6 and members,'R24_THIRD_SWAP')
        yield dict(ordinal=ordinal,remove=list(remove),add=list(add),indices=ids,
            identity=fingerprint(sorted(states[i] for i in ids)),family_owner=members[0],families=members)


def planned_summary(center):
    """Freeze the mathematical space before enumerating any candidate."""
    classes=Counter();deletions={}
    for remove in effective_removals(center):
        active=[label for label,r,_,_ in ANCHORS if set(r)<set(remove)]
        count={'p1':2141,'p2,p3':4281,'p1,p2,p3':6420}[','.join(active)]
        classes[count]+=1;deletions[','.join(map(str,remove))]=count
    require(classes=={2141:25,4281:25,6420:1},'R24_REMOVAL_CLASSES')
    return dict(status='PASS',declared_candidates=DECLARED,owner_counts=dict(p1=55666,p2=55665,p3=55639),
        family_sizes=[55666]*3,pairwise_intersections=[1,1,26],triple_intersection=0,intersection=28,
        deletion_triple_counts=deletions,effective_removal_triples=51,
        independent_count_formula='25*2141+25*4281+6420=166970',identity_order_sha256=None,
        operation_order_sha256=None,pair_order_sha256=None,deferred_until_after_freeze=True,
        traversal='unordered removal triple numeric lexicographic then unordered addition triple numeric lexicographic',
        symmetric_difference_from_S=6,disjoint_from_R19_single_R22_double_and_R21_declared_third=True,
        R21_disjointness_reason='R21 requires 1440 and 218/1876; R24 requires 1118 and 196/2/640; at least four distinct additions',
        history_filter_applied=False,candidate_REUSED=0,earlier_identity_disjointness_claimed=False)


def summary(center, donors, states, check=lambda:None):
    identities,owners,deletions=set(),Counter(),Counter()
    families_seen=Counter();order=hashlib.sha256();op_order=hashlib.sha256();first=last=None
    for row in iter_candidates(center,donors,states,check):
        require(row['identity'] not in identities,'R24_DUPLICATE_IDENTITY')
        identities.add(row['identity']);owners[row['family_owner']]+=1;deletions[tuple(row['remove'])]+=1
        families_seen.update(row['families'])
        order.update((row['identity']+'\n').encode())
        op_order.update((','.join(map(str,row['remove']+row['add']))+'\n').encode())
        first=row if first is None else first;last=row
    require(len(identities)==DECLARED and dict(owners)==dict(p1=55666,p2=55665,p3=55639),'R24_EXACT_UNION')
    require(len(deletions)==51 and Counter(deletions.values())=={2141:25,4281:25,6420:1},'R24_DELETION_TRIPLES')
    require(dict(families_seen)==dict(p1=55666,p2=55666,p3=55666),'R24_FAMILY_MEMBERSHIP_COUNTS')
    result=planned_summary(center)
    result.update(unique_identities=len(identities),identity_order_sha256=order.hexdigest(),
        operation_order_sha256=op_order.hexdigest(),pair_order_sha256=op_order.hexdigest(),
        pair_order_sha256_compatibility_name_means_triples=True,first=first,last=last,
        deferred_until_after_freeze=False,owner_counts=dict(owners))
    return result
