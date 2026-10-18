import sys
import os
import json
import argparse

def get_tasks_file():
    return os.environ.get("AIOS_TASKS_FILE", "/ai/state/tasks.json")

def load_tasks():
    path = get_tasks_file()
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump({"tasks": []}, f)
        except Exception as e:
            sys.stderr.write(f"Error creating tasks file: {e}\n")
            sys.exit(1)
    
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        sys.stderr.write(f"Error reading tasks file: {e}\n")
        sys.exit(1)

def save_tasks(data):
    path = get_tasks_file()
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        sys.stderr.write(f"Error saving tasks file: {e}\n")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(prog="tasks", add_help=False)
    subparsers = parser.add_subparsers(dest="command")

    # add
    add_p = subparsers.add_parser("add")
    add_p.add_argument("title")
    add_p.add_argument("--acceptance", default="")
    add_p.add_argument("--depends", default="")
    add_p.add_argument("--notes", default="")

    # list
    subparsers.add_parser("list")

    # next
    subparsers.add_parser("next")

    # done
    done_p = subparsers.add_parser("done")
    done_p.add_argument("id", type=int)

    # fail
    fail_p = subparsers.add_parser("fail")
    fail_p.add_argument("id", type=int)

    # show
    show_p = subparsers.add_parser("show")
    show_p.add_argument("id", type=int)

    args = parser.parse_args()
    data = load_tasks()
    tasks = data.get("tasks", [])

    if args.command == "add":
        next_id = max([t["id"] for t in tasks], default=0) + 1
        depends = []
        if args.depends:
            try:
                depends = [int(x) for x in args.depends.split(",")]
            except ValueError:
                sys.stderr.write("Error: depends must be comma-separated integers\n")
                sys.exit(1)
        
        task = {
            "id": next_id,
            "title": args.title,
            "depends": depends,
            "status": "pending",
            "acceptance_cmd": args.acceptance,
            "notes": args.notes
        }
        tasks.append(task)
        save_tasks({"tasks": tasks})
        print(next_id)

    elif args.command == "list":
        for t in tasks:
            print(f"{t['id']} {t['status']} {t['title']}")

    elif args.command == "next":
        done_ids = {t["id"] for t in tasks if t["status"] == "done"}
        for t in tasks:
            if t["status"] == "pending":
                if all(dep in done_ids for dep in t["depends"]):
                    print(f"{t['id']} {t['title']}")
                    return
        print("NO_TASK")

    elif args.command == "done":
        found = False
        for t in tasks:
            if t["id"] == args.id:
                t["status"] = "done"
                found = True
                break
        if not found:
            sys.stderr.write(f"Error: Task {args.id} not found\n")
            sys.exit(1)
        save_tasks({"tasks": tasks})

    elif args.command == "fail":
        found = False
        for t in tasks:
            if t["id"] == args.id:
                t["status"] = "failed"
                found = True
                break
        if not found:
            sys.stderr.write(f"Error: Task {args.id} not found\n")
            sys.exit(1)
        save_tasks({"tasks": tasks})

    elif args.command == "show":
        found = False
        for t in tasks:
            if t["id"] == args.id:
                print(json.dumps(t))
                found = True
                break
        if not found:
            sys.stderr.write(f"Error: Task {args.id} not found\n")
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
