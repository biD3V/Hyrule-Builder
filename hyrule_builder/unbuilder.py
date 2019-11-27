# pylint: disable=invalid-name
""" Functions for unbuilding BOTW mods """
from multiprocessing import Pool, cpu_count
from pathlib import Path
from shutil import rmtree

import aamp.converters as ac
import byml
from byml import yaml_util as by
import pymsyt
import sarc
import yaml
from . import AAMP_EXTS, BYML_EXTS, SARC_EXTS, decompress

def _if_unyaz(data: bytes) -> bytes:
    return data if data[0:4] != b'Yaz0' else decompress(data)

def _unbuild_file(f: Path, out: Path, mod: Path, verbose: bool):
    of = out / f.relative_to(mod)
    if not of.parent.exists():
        of.parent.mkdir(parents=True, exist_ok=True)
    if f.suffix in AAMP_EXTS:
        of.with_suffix(f'{f.suffix}.yml').write_bytes(ac.aamp_to_yml(f.read_bytes()))
    elif f.suffix in BYML_EXTS:
        of.with_suffix(f'{f.suffix}.yml').write_bytes(_byml_to_yml(f.read_bytes()))
    elif f.suffix in SARC_EXTS:
        with f.open('rb') as file:
            s = sarc.read_file_and_make_sarc(file)
        if not s:
            return
        _unbuild_sarc(s, of)
        del s
    else:
        of.write_bytes(f.read_bytes())
    if verbose:
        print(f'Unbuilt {f.relative_to(mod).as_posix()}')

def _unbuild_sarc(s: sarc.SARC, output: Path):
    SKIP_SARCS = {'tera_resource.Cafe_Cafe_GX2.release.ssarc'}

    output.mkdir(parents=True, exist_ok=True)
    if any(f.startswith('/') for f in s.list_files()):
        (output / '.slash').write_bytes(b'')

    for sf in s.list_files():
        osf = output / sf
        if sf.startswith('/'):
            osf = output / sf[1:]
        osf.parent.mkdir(parents=True, exist_ok=True)
        ext = osf.suffix
        if ext not in {*SARC_EXTS, *AAMP_EXTS, *BYML_EXTS}:
            osf.write_bytes(s.get_file_data(sf).tobytes())
        elif ext in AAMP_EXTS:
            osf.with_suffix(f'{osf.suffix}.yml').write_bytes(
                ac.aamp_to_yml(s.get_file_data(sf).tobytes())
            )
        elif ext in BYML_EXTS:
            osf.with_suffix(f'{osf.suffix}.yml').write_bytes(
                _byml_to_yml(s.get_file_data(sf).tobytes())
            )
        else:
            if osf.name in SKIP_SARCS:
                osf.write_bytes(s.get_file_data(sf).tobytes())
                continue
            try:
                ss = sarc.SARC(_if_unyaz(s.get_file_data(sf).tobytes()))
                _unbuild_sarc(ss, osf)
                del ss
            except ValueError:
                osf.write_bytes(b'')

    if 'Msg_' in output.name:
        pymsyt.export(output, output)
        rmtree(output)
        output.with_suffix('').rename(output)
    if output.suffix in {'.ssarc', '.sarc'}:
        (output / '.align').write_text(str(s.guess_default_alignment()))

def _byml_to_yml(file_bytes: bytes) -> bytes:
    if not hasattr(_byml_to_yml, 'dumper'):
        _byml_to_yml.dumper = yaml.CDumper
        by.add_representers(_byml_to_yml.dumper)
    return yaml.dump(
        byml.Byml(_if_unyaz(file_bytes)).parse(),
        Dumper=_byml_to_yml.dumper
    ).encode('utf8')

def unbuild_mod(args) -> None:
    mod = Path(args.directory)
    if not ((mod / 'content').exists() or (mod / 'aoc').exists()):
        print('The specified directory is not valid: no content or aoc folder found')
        exit(1)
    out = mod.with_name(f'{mod.name}_unbuilt') if not args.output else Path(args.output)

    files = {f for f in mod.rglob('**/*') if f.is_file()}
    t = min(len(files), cpu_count())
    if args.single or t < 2:
        for f in files:
            _unbuild_file(f, out, mod, args.verbose)
    else:
        from functools import partial
        p = Pool(processes=t)
        p.map(partial(_unbuild_file, mod=mod, out=out, verbose=args.verbose), files)
        p.close()
        p.join()

    print('Unbuilding complete')