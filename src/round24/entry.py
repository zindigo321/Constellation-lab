"""Frozen dispatch inside the independently supervised process tree."""
import argparse
import sys

def main():
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--mode',required=True)
    args,rest=p.parse_known_args()
    sys.argv=[sys.argv[0],*rest]
    if args.mode in {'initialize','preflight','pretests'}:
        from .preparation import main
        return main(args.mode)
    if args.mode=='research':
        from .run import cli
        return cli()
    if args.mode in {'export','finalizer'}:
        from .export import outer_cli
        return outer_cli()
    if args.mode=='observer':
        from .observe import main
        return main()
    if args.mode=='closure':
        from .closure import main
        return main()
    raise ValueError('R24_UNKNOWN_ENTRY_MODE')

if __name__=='__main__':raise SystemExit(main())
