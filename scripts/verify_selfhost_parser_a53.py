#!/usr/bin/env python3
"""A5.3 Sedrava-written arithmetic AST: independently computed Python oracle.

The AST itself comes from executing the Sedrava source using native CLI.
"""
from __future__ import annotations
import json,os,random,re,subprocess,tempfile
from pathlib import Path
from verify_selfhost_parser_a51 import oracle as token_oracle
ROOT=Path(__file__).resolve().parents[1]
PROGRAM=ROOT/"examples/self_host/parser_a53.sdr"
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
PREFIX='state source = "sum==42 # comment"'
ACTIONS=("scan","scan_layout","merge_tokens","parse_expression_program")
PAT=re.compile(r'^([ ]*)([A-Za-z_][A-Za-z_0-9]*) *= *([0-9]+)(?: *([+\-*/]) *([0-9]+))?(?: *([+\-*/]) *([0-9]+))? *(?:#.*)?$')

def oracle(source:str):
    if len(source)>256:raise ValueError("256 scalar source")
    unified=token_oracle(source)
    if len(unified)>100:raise ValueError("token limit")
    nodes=[];stmts=[];base=0
    for line_no,line in enumerate(source.splitlines(keepends=True),1):
        raw=line.rstrip('\n')
        if not raw.strip() or raw.lstrip(' ').startswith('#'):
            base+=len(line);continue
        m=PAT.fullmatch(raw)
        if m is None:raise ValueError("invalid expression grammar")
        spaces,name,num1,op1,num2,op2,num3=m.groups()
        if len(spaces)>32 or len(spaces)%4 or ('\t' in raw) or ('\r' in raw):
            raise ValueError("invalid indentation")
        depth=len(spaces)//4
        if not stmts and depth!=0:raise ValueError("unexpected first indent")
        if op1 is None and op2 is not None:raise ValueError("missing operator")
        if len(stmts)>=16:raise ValueError("max 16 statements")
        nums=[(num1,m.span(3))]
        if num2 is not None:nums.append((num2,m.span(5)))
        if num3 is not None:nums.append((num3,m.span(7)))
        leaf_ids=[]
        for text,(start,end) in nums:
            node_id=len(nodes)+1
            nodes.append(dict(kind="integer",lexeme=text,operator="",
                left_id=0,right_id=0,start=base+start,end=base+end))
            leaf_ids.append(node_id)
        if len(nums)==1:root=leaf_ids[0]
        elif len(nums)==2:
            root=len(nodes)+1
            nodes.append(dict(kind="binary",lexeme="",operator=op1,
                left_id=leaf_ids[0],right_id=leaf_ids[1],
                start=base+nums[0][1][0],end=base+nums[1][1][1]))
        else:
            root=len(nodes)+2
            if op1 in "+-" and op2 in "*/":
                nodes.append(dict(kind="binary",lexeme="",operator=op2,
                    left_id=leaf_ids[1],right_id=leaf_ids[2],
                    start=base+nums[1][1][0],end=base+nums[2][1][1]))
                nodes.append(dict(kind="binary",lexeme="",operator=op1,
                    left_id=leaf_ids[0],right_id=root-1,
                    start=base+nums[0][1][0],end=base+nums[2][1][1]))
            else:
                nodes.append(dict(kind="binary",lexeme="",operator=op1,
                    left_id=leaf_ids[0],right_id=leaf_ids[1],
                    start=base+nums[0][1][0],end=base+nums[1][1][1]))
                nodes.append(dict(kind="binary",lexeme="",operator=op2,
                    left_id=root-1,right_id=leaf_ids[2],
                    start=base+nums[0][1][0],end=base+nums[2][1][1]))
        stmts.append(dict(name=name,expression_id=root,depth=depth,
            line=line_no,start=base+m.start(2),end=base+nums[-1][1][1]))
        if len(nodes)>100:raise ValueError("node budget")
        base+=len(line)
    if not stmts:raise ValueError("empty AST")
    return nodes,stmts,unified

def run(text:str,folder:Path,actions=ACTIONS):
    template=PROGRAM.read_text()
    assert template.count(PREFIX)==1
    file=folder/"fixture.sdr"
    file.write_text(template.replace(PREFIX,"state source = "+json.dumps(text,ensure_ascii=False)))
    return subprocess.run([str(BIN),"run",str(file),*actions],
        capture_output=True,text=True,timeout=45,env={"PATH":"/nonexistent","LC_ALL":"C"})

def main():
    positives=[
       "a=1","a=1+2","a=1+2*3","a=1*2+3","a=1+2-3",
       "a=8/2/2","a=2*3*4","a=7-2*2","a=9/3+7","a=10*2-5",
       "a=1+2/3","a=1-2-3","a=3/2*4","a=0/4-2",
       "# comment\na=1+2*3","a=1 # comment\n\n    b=2*3+4\nc=8",
       "a=1\n    b=2\n        c=3+4\n    d=6*3\nend=9",
       "abc=0123 # OK","sum=1 + 2 * 3","x=1\n    # skipped\n    y=3/1-2",
    ]
    negatives=[
       "", " # comment", "a=", "a=1+","a=1+2*","a=1+2+3+4",
       "a=-1","a=+1","a=1*(2+3)","a=x+2","a=1^2",
       "a=1//2","a=1**2","a=1+2.1","a=1+2 3","a=1+2\n  b=3",
       " a=2","a=1\n\tb=2","a=1\n    b=2\n c=3",
       "а=1","a=1; b=2","a=1\n    b=2+3*4*5",
       "a"*257+"=1",
    ]
    rng=random.Random(0xA53)
    for _ in range(17):
        lines=[]
        for j in range(rng.randint(1,4)):
            depth=0 if j==0 else rng.randrange(0,4)
            nums=[str(rng.randrange(0,1000)) for _ in range(rng.randint(1,3))]
            ops=[rng.choice("+-*/") for _ in range(len(nums)-1)]
            expr=nums[0]+''.join(" "+op+" "+n for op,n in zip(ops,nums[1:]))
            lines.append(" "*(depth*4)+f"p{j} = "+expr)
        source="\n".join(lines)
        try:oracle(source)
        except ValueError:negatives.append(source)
        else:positives.append(source)
    with tempfile.TemporaryDirectory(prefix="sedrava-a53-ast-") as temp:
        folder=Path(temp)
        for idx,source in enumerate(positives):
            expected_nodes,expected_statements,expected_tokens=oracle(source)
            p=run(source,folder)
            assert p.returncode==0,(idx,repr(source),p.stderr,p.stdout[:150])
            result=json.loads(p.stdout)
            fields=("kind","lexeme","operator","left_id","right_id","start","end")
            nodes=[{k:n[k] for k in fields} for n in result["program_expr_nodes"]["items"]]
            stmts=[{k:n[k] for k in ("name","expression_id","depth","line","start","end")}
                for n in result["program_expr_statements"]["items"]]
            actual_tokens=[{k:n[k] for k in ("kind","lexeme","offset","end","line","column","level")}
                for n in result["unified_tokens"]["items"]]
            assert nodes==expected_nodes,(idx,repr(source),nodes,expected_nodes)
            assert stmts==expected_statements,(idx,repr(source),stmts,expected_statements)
            assert actual_tokens==expected_tokens,(idx,"A5.1 merge mismatch")
            assert [n["id"] for n in result["program_expr_nodes"]["items"]]==list(range(1,len(nodes)+1))
            assert [n["id"] for n in result["program_expr_statements"]["items"]]==list(range(1,len(stmts)+1))
            assert result["program_expr_depth"]==0
            assert result["program_expr_cursor"]==len(actual_tokens)+1
        for idx,source in enumerate(negatives):
            try:oracle(source)
            except ValueError: pass
            else:raise AssertionError(("invalid fixture accepted by oracle",idx))
            p=run(source,folder)
            assert p.returncode!=0,(idx,repr(source),p.stdout[:250],p.stderr)
        assert run("a=1",folder,("parse_expression_program",)).returncode!=0
        assert run("a=1",folder,ACTIONS+("parse_expression_program",)).returncode!=0
    print(f"PASS A5.3: {len(positives)} accepted / {len(negatives)} rejected sources")
    print("PASS A5.3: binary precedence, left-association, AST IDs/spans, layout depths, A5.1 token parity")
    print("LIMIT: only 1..3 integer terms per assignment; not a full language parser or self-hosted compiler")

if __name__=="__main__":main()
