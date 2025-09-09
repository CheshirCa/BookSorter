#!/usr/bin/env python3
# sort_books.py

from __future__ import annotations
import argparse
import logging
import os
import shutil
import sys
import re
from typing import List, Dict, Any, Optional

try:
    import yaml
except Exception:
    yaml = None

# ---------------- helpers ----------------

def win_long_path(path: str) -> str:
    if os.name != 'nt':
        return path
    ab = os.path.abspath(path)
    if ab.startswith('\\\\?\\'):
        return ab
    if ab.startswith('\\\\'):
        return '\\\\?\\UNC\\' + ab.lstrip('\\\\')
    return '\\\\?\\' + ab

def normalize_name(name: str) -> str:
    s = re.sub(r'[._\-]+', ' ', name)
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()

def splitext_nodot(p: str) -> str:
    _, ext = os.path.splitext(p)
    return ext[1:].lower() if ext else ''

# ---------------- patterns ----------------

class Pattern:
    def __init__(self, raw: str):
        self.raw = raw.strip()
        self.alternatives = [alt.strip() for alt in re.split(r'\s*\|\s*', self.raw) if alt.strip()]
        self.priority = max(len(alt) for alt in self.alternatives) if self.alternatives else len(self.raw)

    def matches(self, text_norm: str) -> bool:
        for alt in self.alternatives:
            if alt.startswith('regex:'):
                pattern = alt[len('regex:'):]
                try:
                    if re.search(pattern, text_norm, flags=re.IGNORECASE | re.UNICODE):
                        return True
                except re.error:
                    logging.debug("Invalid regex pattern: %s", pattern)
            else:
                if '*' in alt:
                    tokens = [normalize_name(t) for t in alt.split('*') if t.strip()]
                    if all(tok in text_norm for tok in tokens):
                        return True
                else:
                    tok = normalize_name(alt)
                    if tok in text_norm:
                        return True
        return False

# ---------------- groups ----------------

class Group:
    def __init__(self, name: str, parent: Optional['Group']=None):
        self.name = name
        self.parent = parent
        self.subgroups: List[Group] = []
        self.include_patterns: List[Pattern] = []
        self.exclude_patterns: List[Pattern] = []

    @property
    def full_name(self) -> str:
        parts = []
        g = self
        while g:
            parts.append(g.name)
            g = g.parent
        return os.path.join(*reversed(parts))

    def add_subgroup(self, g: 'Group'):
        self.subgroups.append(g)

    def __repr__(self):
        return f"<Group {self.full_name}>"

# ---------------- config ----------------

def build_groups_from_config(config: Dict[str, Any]) -> List[Group]:
    groups = []

    def build_node(node: Dict[str, Any], parent: Optional[Group]=None) -> Group:
        name = node.get('name') or node.get('Group')
        if not name:
            raise ValueError("Group without a name")
        g = Group(name=str(name), parent=parent)
        for key in ('include', 'Include'):
            if key in node:
                items = node[key]
                if isinstance(items, str):
                    items = [items]
                g.include_patterns += [Pattern(str(it)) for it in items]
        for key in ('exclude', 'Exclude'):
            if key in node:
                items = node[key]
                if isinstance(items, str):
                    items = [items]
                g.exclude_patterns += [Pattern(str(it)) for it in items]
        for child in node.get('groups', []) or node.get('Groups', []):
            if isinstance(child, dict):
                g.add_subgroup(build_node(child, parent=g))
        return g

    top_nodes = config.get('groups') or config.get('Groups') or []
    if isinstance(top_nodes, dict):
        top_nodes = [top_nodes]
    for tn in top_nodes:
        if isinstance(tn, dict):
            groups.append(build_node(tn))
    return groups

# ---------------- matching (вариант A) ----------------

def file_matches_group_name(file_path: str, group: Group) -> bool:
    if not group.include_patterns:
        return False  # Родительская группа без include не подходит сама по себе

    base = os.path.basename(file_path)
    name_no_ext, _ = os.path.splitext(base)
    normalized = normalize_name(name_no_ext)

    if not any(p.matches(normalized) for p in group.include_patterns):
        return False
    if any(p.matches(normalized) for p in group.exclude_patterns):
        return False
    return True

def match_file_recursively(file_path: str, group: Group) -> List[Group]:
    matches = []
    for sub in group.subgroups:
        matches.extend(match_file_recursively(file_path, sub))
    if not matches and file_matches_group_name(file_path, group):
        matches.append(group)
    return matches

# ---------------- file ops ----------------

def ensure_dir(path: str, dry_run=False):
    if dry_run:
        logging.info("[dry-run] mkdir %s", path)
    else:
        os.makedirs(path, exist_ok=True)

def create_hardlink_or_copy(source: str, link_path: str, dry_run=False):
    os.makedirs(os.path.dirname(link_path), exist_ok=True)
    if dry_run:
        logging.info("[dry-run] link %s -> %s", source, link_path)
        return
    try:
        s = win_long_path(source)
        l = win_long_path(link_path)
        if os.path.exists(l):
            os.remove(l)
        os.link(s, l)
        logging.info("Hardlink: %s", link_path)
    except Exception as e:
        logging.warning("Hardlink failed, copying: %s", e)
        shutil.copy2(source, link_path)

# ---------------- drive check ----------------

def check_same_drive(src_dir: str, dst_dir: str) -> bool:
    if os.name != 'nt':
        return True
    src_drive = os.path.splitdrive(os.path.abspath(src_dir))[0].lower()
    dst_drive = os.path.splitdrive(os.path.abspath(dst_dir))[0].lower()
    if src_drive != dst_drive:
        logging.warning(
            "Source (%s) и Destination (%s) на разных дисках. Hardlinks не будут работать. Используется копирование.",
            src_dir, dst_dir
        )
        return False
    return True

# ---------------- processing ----------------

def process_all(src_dir: str, dst_dir: str, top_groups: List[Group], dry_run=False, move=False):
    files_to_delete = []
    hardlink_supported = check_same_drive(src_dir, dst_dir)

    for root, _, files in os.walk(src_dir):
        for fname in files:
            src_path = os.path.join(root, fname)
            matches = []
            for g in top_groups:
                matches.extend(match_file_recursively(src_path, g))

            if not matches:
                continue

            matches_sorted = sorted(matches, key=lambda g: -max((p.priority for p in g.include_patterns), default=0))
            primary = matches_sorted[0]
            dst_primary = os.path.join(dst_dir, primary.full_name, fname)

            ensure_dir(os.path.dirname(dst_primary), dry_run)
            if dry_run:
                logging.info("[dry-run] copy %s -> %s", src_path, dst_primary)
            else:
                shutil.copy2(src_path, dst_primary)

            for g in matches_sorted[1:]:
                link_path = os.path.join(dst_dir, g.full_name, fname)
                if hardlink_supported:
                    create_hardlink_or_copy(dst_primary, link_path, dry_run)
                else:
                    dst_fallback = os.path.join(dst_dir, g.full_name, fname)
                    ensure_dir(os.path.dirname(dst_fallback), dry_run)
                    if dry_run:
                        logging.info("[dry-run] copy fallback %s -> %s", dst_primary, dst_fallback)
                    else:
                        shutil.copy2(dst_primary, dst_fallback)

            if move:
                files_to_delete.append(src_path)

    if move:
        for f in files_to_delete:
            if dry_run:
                logging.info("[dry-run] delete %s", f)
            else:
                try:
                    os.remove(f)
                    logging.info("Deleted: %s", f)
                except Exception as e:
                    logging.error("Failed to delete %s: %s", f, e)

# ---------------- logging ----------------
def setup_logging(level_name: str, logfile: Optional[str]=None):
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s: %(message)s")
    if logfile:
        fh = logging.FileHandler(logfile, encoding='utf-8')
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logging.getLogger().addHandler(fh)

# ---------------- main ----------------
def main():
    global yaml
    p = argparse.ArgumentParser()
    p.add_argument('--config','-c',default='config.yaml')
    p.add_argument('--src','-s',default='.')
    p.add_argument('--dst','-d',default='./sorted')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--move', action='store_true')
    p.add_argument('--log', default=None)
    p.add_argument('--log-level', default='INFO')
    p.add_argument('--demo-config', action='store_true')

    args = p.parse_args()

    setup_logging(args.log_level, args.log)

    if args.demo_config:
        demo_cfg = {
            'groups': [
                {'name': 'IT', 'groups': [
                    {'name': 'Programming', 'groups': [
                        {'name': 'Python', 'include': ['Python']},
                        {'name': 'Rust', 'include': ['Rust']},
                        {'name': 'Java', 'include': ['Java']},
                        {'name': 'PHP', 'include': ['PHP*MySQL', 'PHP']},
                        {'name': 'JavaScript', 'include': ['JavaScript', 'JS']},
                        {'name': 'Go', 'include': ['GoLang', 'Go']},
                        {'name': 'C++', 'include': ['regex:C\\+\\+', 'Cplusplus']},
                        {'name': 'C', 'include': ['C programming']}
                    ]},
                    {'name': 'Systems', 'groups': [
                        {'name': 'Windows', 'include': ['Windows', 'WinServer', 'Windows10', 'Windows11'], 'exclude': ['Office']},
                        {'name': 'Linux', 'include': ['Linux', 'Ubuntu', 'Debian', 'Fedora']},
                        {'name': 'macOS', 'include': ['macOS', 'OSX', 'Macintosh']}
                    ]},
                    {'name': 'Applications', 'groups': [
                        {'name': 'Office', 'include': ['Office', 'Office365', 'Microsoft Word', 'Excel', 'PowerPoint'], 'exclude': ['Linux', 'macOS']},
                        {'name': 'Adobe', 'include': ['Photoshop', 'Illustrator', 'Acrobat']},
                        {'name': 'IDEs', 'include': ['PyCharm', 'IntelliJ', 'Visual Studio', 'VSCode', 'Eclipse']}
                    ]}
                ]},
                {'name': 'Science', 'groups': [
                    {'name': 'Physics', 'include': ['Physics', 'Физика', 'Quantum', 'Mechanics']},
                    {'name': 'Chemistry', 'include': ['Chemistry', 'Химия', 'Organic', 'Lab']},
                    {'name': 'Biology', 'include': ['Biology', 'Биология'], 'groups': [
                        {'name': 'For_Kids', 'include': ['детям', 'for_kids', 'kids']}
                    ]},
                    {'name': 'Mathematics', 'include': ['Math', 'Математика', 'Statistics', 'Алгебра']},
                    {'name': 'Astronomy', 'include': ['Astronomy', 'Stars', 'Cosmos', 'Космос']},
                    {'name': 'General', 'include': ['Science', 'Наука']}
                ]},
                {'name': 'Kids', 'include': ['Fairy_tales', 'Stories', 'Истории', 'детям', 'Children']},
                {'name': 'Arts', 'include': ['Art', 'Painting', 'Music', 'Музыка', 'Живопись']},
                {'name': 'Literature', 'include': ['Novel', 'Poetry', 'Поэзия', 'Роман']}
            ]
        }
        with open('config_demo.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(demo_cfg, f, allow_unicode=True)
        logging.info("Demo config 'config_demo.yaml' created")
        return

    if yaml is None:
        logging.error("PyYAML is required")
        return

    if not os.path.exists(args.config):
        logging.error("Config file %s not found", args.config)
        return

    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    groups = build_groups_from_config(cfg)

    process_all(args.src, args.dst, groups, dry_run=args.dry_run, move=args.move)

if __name__ == '__main__':
    main()
