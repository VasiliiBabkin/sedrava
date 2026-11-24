#!/usr/bin/env python3
"""Independent expected scalar signatures and semantic errors, analysis in Sedrava."""
import json,subprocess,tempfile,os
from pathlib import Path
import verify_selfhost_parser_a51 as base
PROGRAM=base.ROOT/"examples/self_host/parser_a57.sdr"
ACTIONS=("scan","scan_layout","merge_tokens","validate_blocks","parse_expression_program","load_symbols","analyze")
def run(src,decl,folder,actions=ACTIONS):
    lines=PROGRAM.read_text().splitlines()
    lines=["state declarations = "+json.dumps(decl,ensure_ascii=False) if l.startswith("state declarations = ") else "state source = "+json.dumps(src,ensure_ascii=False) if l.startswith("state source = ") else l for l in lines]
    app=folder/"case.sdr";app.write_text("\n".join(lines)+"\n")
    return subprocess.run([str(base.BIN),"run",str(app),*actions],capture_output=True,text=True,timeout=35,env={"PATH":"/nonexistent","LC_ALL":"C"})
def main():
    context="x v i\ny v i\nflag v b\nr v i\nok v b\ns v t\nf f ii i\nready f i b\nzero f - i\nmixed f ib i\nlabel f - t"
    valid=[("r=f(x,y)+zero()",["i"]),("ok=ready(x) and not flag",["b"]),("r=mixed(f(x,y),flag)",["i"]),("s=label()",["t"]),("ok=s==label()",["b"]),("r=-x*2",["i"]),("if ready(x):\n        r=f(x,y)\n    else:\n        r=zero()",["i","i"])]
    bad=[("r=missing", "unknown_symbol"),("r=nope(x)","unknown_symbol"),("r=f","function_used_as_value"),("r=x()","not_callable"),("r=f(x)","argument_signature"),("r=f(x,flag)","argument_signature"),("r=zero(x)","argument_signature"),("r=flag+1","operand_type"),("ok=x and flag","operand_type"),("r=not x","operand_type"),("ok=x==flag","operand_type"),("r=x/y","unsupported_operator"),("r=label()","assignment_type"),("if x:\n        r=1","condition_type"),("z=1","unknown_assignment"),("f=1","not_assignable")]
    with tempfile.TemporaryDirectory(prefix="sedrava-a57-") as t:
        folder=Path(t)
        for body,types in valid:
            src="action go:\n    "+body
            p=run(src,context,folder);assert p.returncode==0,(src,p.stderr)
            d=json.loads(p.stdout);assert d["semantic_done"] and d["context_done"] and d["semantic_error"]=="",(src,d["semantic_error"])
            ns=d["node_types"]["items"];assert len(ns)==len(d["program_expr_nodes"]["items"])
            assert [ns[n["expression_id"]-1]["kind"] for n in d["program_expr_statements"]["items"]]==types
            for n in d["program_expr_nodes"]["items"]:
                if n["kind"] in ("call","identifier"):
                    assert d["symbols"]["items"][ns[n["id"]-1]["symbol_id"]-1]["name"]==n["lexeme"]
        for body,err in bad:
            src="action go:\n    "+body
            p=run(src,context,folder);assert p.returncode==0,(src,p.stderr)
            d=json.loads(p.stdout);assert d["semantic_done"] and d["semantic_error"]==err,(src,d["semantic_error"],err)
            assert 0<=d["semantic_start"]<d["semantic_end"]<=len(src)
        for decl,err in [("r v i\nr v b","duplicate_symbol"),("r v q","invalid_declaration"),("f f iz i","invalid_signature"),("if v i","invalid_symbol_name"),("f f iiiiiiiii i","signature_budget")]:
            p=run("action go:\n    r=1",decl,folder);assert p.returncode==0,p.stderr
            d=json.loads(p.stdout);assert d["semantic_error"]==err,(decl,d["semantic_error"],err)
        assert run("action go:\n    r=1",context,folder,ACTIONS[:-2]+("analyze",)).returncode!=0
        assert run("action go:\n    r=1",context,folder,ACTIONS+("analyze",)).returncode!=0
    print("PASS A5.7: 7 typed programs, 16 semantic errors, 5 declaration errors, 2 sequencing guards")
if __name__=="__main__":main()
