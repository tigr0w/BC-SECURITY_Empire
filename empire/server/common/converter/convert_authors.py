import fnmatch
import os

from ruamel.yaml import YAML

yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.width = 120


author_names = {
    "@harmj0y": "Will Schroeder",
    "@hubbl3": "Jake Krasnov",
    "@Cx01N": "Anthony Rose",
    "@S3cur3Th1sSh1t": "",
    "@mattifestation": "Matt Graeber",
    "@joevest": "Joe Vest",
    "@424f424f": "",
    "@gentilkiwi": "Benjamin Delpy",
    "@tifkin_": "Lee Christensen",
    "@JosephBialek": "Joseph Bialek",
    "matterpreter": "Matt Hand",
    "@n00py": "",
    "@_wald0": "Andy Robbins",
    "@cptjesus": "Rohan Vazarkar",
    "@xorrior": "Chris Ross",
    "@TweekFawkes": "Bryce Kunz",
}


author_links = {
    "@harmj0y": "https://twitter.com/harmj0y",
    "@hubbl3": "https://twitter.com/_hubbl3",
    "@Cx01N": "https://twitter.com/Cx01N_",
    "@S3cur3Th1sSh1t": "https://twitter.com/ShitSecure",
    "@mattifestation": "https://twitter.com/mattifestation",
    "@joevest": "https://twitter.com/joevest",
    "@424f424f": "https://twitter.com/424f424f",
    "@gentilkiwi": "https://twitter.com/gentilkiwi",
    "@tifkin_": "https://twitter.com/tifkin_",
    "@JosephBialek": "https://twitter.com/JosephBialek",
    "matterpreter": "https://twitter.com/matterpreter",
    "@n00py": "https://twitter.com/n00py1",
    "@_wald0": "https://twitter.com/_wald0",
    "@cptjesus": "https://twitter.com/cptjesus",
    "@xorrior": "https://twitter.com/xorrior",
    "@TweekFawkes": "https://twitter.com/TweekFawkes",
}


def convert_old_author(author):
    name = ""
    handle = ""
    link = ""
    if author.startswith("@"):
        handle = author
        if handle in author_names:
            name = author_names[handle]
        if handle in author_links:
            link = author_links[handle]
    else:
        name = author

    return {"name": name, "handle": handle, "link": link}


if __name__ == "__main__":
    # yaml.add_representer(type(None), represent_none)
    root_path = "../../modules"
    pattern = "*.yaml"
    for root, _dirs, files in os.walk(root_path):
        for filename in fnmatch.filter(files, pattern):
            try:
                file_path = os.path.join(root, filename)

                # don't load up any of the templates
                if fnmatch.fnmatch(filename, "*template.yaml"):
                    continue
                if fnmatch.fnmatch(filename, "*Covenant.yaml"):
                    continue

                with open(file_path) as stream:
                    yaml_dict = yaml.load(stream)
                    author_handles = yaml_dict["authors"]

                    if author_handles is None:
                        continue
                    if len(author_handles) > 0:
                        if not isinstance(author_handles[0], str):
                            continue

                    # split any author strings within the list with commas and convert to list
                    author_list = []
                    for author in author_handles:
                        author_list.extend(author.split(","))

                    new_authors = list(map(convert_old_author, author_list))

                    yaml_dict["authors"] = new_authors

                with open(file_path, "w") as out:
                    yaml.dump(yaml_dict, out)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
