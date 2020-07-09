import re
import sys
from shutil import copyfile, rmtree
from distutils.dir_util import copy_tree
from pathlib import Path
import yaml
import collections
import pydash
import hiyapyco
import os.path

def mkdir(path):
   Path(path).mkdir(parents=True, exist_ok=True)

def wordify(name):
   return pydash.strings.start_case(name)

def ymlify(data):
   return yaml.dump(data, default_flow_style=None, sort_keys=False)

def dict_fmerge(base_dct, merge_dct, add_keys=True):
   rtn_dct = base_dct.copy()
   if add_keys is False:
      merge_dct = {key: merge_dct[key] for key in set(rtn_dct).intersection(set(merge_dct))}

   rtn_dct.update({
      key: dict_fmerge(rtn_dct[key], merge_dct[key], add_keys=add_keys)
      if isinstance(rtn_dct.get(key), dict) and isinstance(merge_dct[key], dict)
      else merge_dct[key]
      for key in merge_dct.keys()
   })
   return rtn_dct

def key_fix(key):
   key = key.replace("Params", "params")
   key = key.replace("Menus", "menu")
   key = key.replace("Title", "title")
   key = key.replace("BaseURL", "baseURL")
   return key

def cms_point(pointer, key, field_type, level, key_root = "", type = "", isConfig = False):
   if isConfig:
      level = 2

      nested_key = re.match(r'^(?P<parent>[\w\d]+?)\.(?P<children>.*)$', key)
      if nested_key:
         root_key = nested_key.group("parent")
         child_keys = nested_key.group("children")
         _current_pointer = cms_point(pointer, root_key, "$", 2, isConfig = True)
         return cms_point(_current_pointer, child_keys, field_type, level, key_root, type, isConfig = True)
      else:
         # we fix key for builtin hugo variables
         key = key_fix(key)
      
      for f in pointer:
         if f["name"] == key:
            return f["fields"]
   # visible widget for optionals
   visible_widget = {
      "name": "visible",
      "label": "Visible",
      "widget": "boolean"
   }
   if field_type == "$" or field_type == "-":
      if level == 0:
         widget = {
            "name": key,
            "label": wordify(key),
            "editor": {"preview": False},
            "files": []
         }
         pointer.append(widget)
         pointer = widget["files"]
         return pointer
      elif level == 1:
         widget = {
            "file": "data/{}/{}.yml".format(key_root, key),
            "label": wordify(key),
            "name": key,
            "fields": []
         }
         if type == "optional":
            widget["fields"].append(visible_widget)
         pointer.append(widget)
         pointer = widget["fields"]
         return pointer
      else:
         widget_type = "object" if field_type == "$" else "list"
         widget = {
            "label": wordify(key),
            "name": key,
            "widget": widget_type,
            "fields": []
         }
         if field_type == "-": widget["allow_add"] = True
         if field_type == "$" and type == "optional":
            widget["fields"].append(visible_widget)
         pointer.append(widget)
         pointer = widget["fields"]
         return pointer
   else:
      widget_type = None
      if field_type == "":
         widget_type = "string"
      else:
         widget_type = field_type
      
      if field_type == "omit": widget_type = "hidden"
      if widget_type == None: raise Exception("Not valid widget type")
      widget = {
         "label": wordify(key),
         "name": key,
         "widget": widget_type
      }
      pointer.append(widget)
      return pointer
      

def point(current_pointer, key, value = "object"):
   nested_key = re.match(r'^(?P<parent>[\w\d]+?)\.(?P<children>.*)$', key)
   if nested_key:
      root_key = nested_key.group("parent")
      child_keys = nested_key.group("children")
      _current_pointer = point(current_pointer, root_key)
      return point(_current_pointer, child_keys, value)
   else:
      # we fix key for builtin hugo variables
      key = key_fix(key)
   
   if key not in current_pointer:
      if value == "object": 
         current_pointer[key] = {}
      elif value == "optional_object": 
         current_pointer[key] = {}
         current_pointer[key]["visible"] = True
      elif value == "list": 
         current_pointer[key] = []
      else: current_pointer[key] = value
   pointer = current_pointer[key]
   return pointer

def parseFiletype(filetype, file, cms = False):
   if cms:
      _cms_pointer = cms_fields[filetype]
      parse(rexs[filetype], file.og, database[filetype], filetype, _file = file, cms_pointer = _cms_pointer)
   else:
      parse(rexs[filetype], file.og, database[filetype], filetype, _file = file)

class File:
   def __init__(self, contents):
      self.og = contents
      self.replaced = contents

   def replaceInFile(self, filetype, o, type, level, len = None, root = "", field_type = ""):
      base_path = None
      if filetype == "data":
         if True:
         # if root == "homepage":
            if level == 0: return
            if level == 1: base_path = ".Site.Data." + root
            if level >= 2: base_path = ""
         else:
            if level == 0: return
            if level == 1: base_path = "(index .Site.Data .File.TranslationBaseName)"
            if level >= 2: base_path = ""

         
      if filetype == "config":
         base_path = "$.Site" if level == 0 else ""
      
      if base_path == None: raise Exception("base_path with value None")

      # for nested 
      if type == '$' or type == '-':
         key =  re.sub(r'^([^\s\|]+)\|?.*', r'\1', o["nest_name"])
         path = base_path + "." + key

         function = ""
         if type == "$": function = "with "
         elif type == "-": function = "range "
         else: raise Exception("Not valid type on replaceInFile")

         og_open = o["ind"] + o["nest_open"]
         to_open = o["ind"] + "{{ " + function + path + " }}"

         og_close = o["ind"] + o["nest_close"]
         to_close = o["ind"] + "{{ end }}"

         # if optional
         if type == "$" and field_type == "optional":
            to_open = o["ind"] + "{{ " + function + path + " }}{{ if .visible }}"
            to_close = o["ind"] + "{{ end }}{{ end }}"

         self.replaced = self.replaced.replace(og_open, to_open, 1)
         self.replaced = self.replaced.replace(og_close, to_close, 1)
         
      if type == "value":
         has_html_rex = r'<\s*(?P<tag>[\w]{1,7})[^>]*>(.*?)<\s*/\s*(?P=tag)>'
         pipe = ""
         omit = False

         if field_type == "markdown":
            pipe = " | markdownify"
         elif field_type == "omit":
            omit = True
         else:
            has_html = re.search(has_html_rex, o["value_contents"]);
            if has_html:
               pipe = " | safeHTML"

         key =  re.sub(r'^([^\s\|]+)\|?.*', r'\1', o["value_name"])
         path = base_path + "." +key
         og = o[0]
         to = "{{ "+ path + pipe +" }}" if not omit else ""
         self.replaced = self.replaced.replace(og, to, 1)
      if type == "list":
         og = o[0]
         to = ""
         if len == 1:
            to = o["element_contents"]
         
         self.replaced = self.replaced.replace(og, to, 1)


database = {
   "config": {},
   "data": {},
   "content": {}
}

cms_fields = {
   "config": [],
   "data": [],
   "content": []
}

rexs = {
   "config": {
      "nest": r'(?P<ind>\n[\t ]*?)(?P<nest_open>\[\[(?P<nest_type>[^\s\w\d])(?P<nest_name>[\S]*?)\]\])(?P<nest_contents>.*?)(?P=ind)(?P<nest_close>\[\[\Send\]\])',
      "value": r'\[\[(?P<value_name>[^\s:]+):(?P<value_contents>.*?)\]\]',
      "element": r'\[\[\[(?P<element_contents>.*?)\]\]\]'
   },
   "data": {
      "nest": r'(?P<ind>\n[\t ]*?)(?P<nest_open>{{(?P<nest_type>[^\s\w\d])(?P<nest_name>[\S]*?)}})(?P<nest_contents>.*?)(?P=ind)(?P<nest_close>{{\Send}})',
      "value": r'{{(?P<value_name>[^\s:]+):(?P<value_contents>.*?)}}',
      "element": r'{{{(?P<element_contents>.*?)}}}'
   }
}

def parse(rex, contents, pointer, filetype, level = -1, key_root = "", write = True, _file = "", cms_pointer = False):
   level = level + 1
   rex_str = "|".join([rex["nest"], rex["element"], rex["value"]]) 
   ocs = re.finditer(rex_str, contents, re.S)
   for o in ocs:
      if o["nest_name"]: #if nest (list or object)
         type = o["nest_type"]

         field_type = ""
         key = ""
         fullkey = re.match(r'^(?P<key>[^\s\|]+)\|(?P<type>\S+)|^(?P<key2>[^\s\|]+)', o["nest_name"]).groupdict()
         if fullkey["key2"] == None:
            key = fullkey["key"]
            field_type = fullkey["type"]
         else:
            key = fullkey["key2"]

         _contents = o["nest_contents"]

         if type == "-":
            _pointer = point(pointer, key, "list")
         elif type == "$":
            # if root level, we add root key for replaces
            if level == 0: key_root = key 

            if field_type == "optional":
               _pointer = point(pointer, key, "optional_object")
            else:
               _pointer = point(pointer, key, "object")
         else:
            raise Exception("No valid nest type")

         _cms_pointer = False
         if cms_pointer != False: 
            _cms_pointer = cms_point(cms_pointer, key, type, level, key_root, field_type, isConfig = (filetype == "config"))

         _file.replaceInFile(filetype, o, type, level, root = key_root, field_type = field_type)
         parse(rex, _contents, _pointer, filetype, level, key_root, True, _file, _cms_pointer)

      if o["element_contents"]: # if element form list
         pointer.append({})
         _pointer = pointer[-1]

         #we will pass the length of the current list
         list_index = len(pointer)
         _file.replaceInFile(filetype, o, "list", level, list_index)

         parse(rex, o["element_contents"], _pointer, filetype, level, key_root, list_index == 1, _file, cms_pointer)

      if o["value_name"]: # if value
         field_type = ""
         key = ""
         fullkey = re.match(r'^(?P<key>[^\s\|]+)\|(?P<type>\S+)|^(?P<key2>[^\s\|]+)', o["value_name"]).groupdict()
         if fullkey["key2"] == None:
            key = fullkey["key"]
            field_type = fullkey["type"]
         else:
            key = fullkey["key2"]

         point(pointer, key, o["value_contents"])
         if write:
            if cms_pointer != False: 
               cms_point(cms_pointer, key, field_type, level, key_root, isConfig = (filetype == "config"))
            _file.replaceInFile(filetype, o, "value", level, root = key_root, field_type = field_type)
   level = level - 1

# MAKE SURE FOLDERS EXIST
# MAKE SURE FOLDERS EXIST
# MAKE SURE FOLDERS EXIST
# Path(test_path).mkdir(parents=True, exist_ok=True)

class Parser:
   def __init__(self, parser_config):
      website_folder = 'website/'
      parser_folder = parser_config["template_folder"]
      head_scripts_check = False
      footer_scripts_check = False

      rmtree('website', ignore_errors=True)
      copy_tree('_website', 'website')

      # create folders
      mkdir(website_folder + "layouts/partials/")
      mkdir(website_folder + "layouts/partials/pages/")
      mkdir(website_folder + "content/")

      # Static assets to static folder
      for f in parser_config["static_assets"]:
         fr = parser_folder + f
         to = website_folder + "static/" + f
         if f[-1] == "/":
            copy_tree(fr, to)
         else:
            copyfile(fr, to)

      # Clean collections in admin config file
      admin_config_path = website_folder + "static/admin/config.yml"
      _admin_config = yaml.load(Path(admin_config_path).read_text(), yaml.FullLoader)
      _admin_config["collections"] = []

      with open(admin_config_path, 'w') as f:
         f.write(ymlify(_admin_config))
         f.close()

      # Get list of files to process
      files = parser_config["files_to_process"]
      for f in files:
         contents = Path(parser_folder + f).read_text()
         file = File(contents)
         parseFiletype("config", file, True)
         parseFiletype("data", file, True)
         # parseFiletype("content", contents)
         
         #clean file of extra break lines, comments, etc
         file = self.clean_file(file)
         
         # We resolve __partials__

         partials_rex = r'(?P<ind>\n[\t ]*?)___(?P<name>[\S]+?)___\n(?P<content>.*?)(?P=ind)___end___'
         partials = re.finditer(partials_rex, file.replaced, re.S)
         for p in partials:
            path = website_folder + "layouts/partials/"+ p["name"]

            content = p["content"]
            # clean tabs
            content = self.clean_indent(content)

            # add scripts for netlifyCMS and my mailer
            if p["name"] == "head.html":
               head_scripts_check = True
               # scss parser
               scss_parser_str = '{{ range $.Site.Params.plugins.scss }}\n{{ $style := resources.Get .url | toCSS }}<link rel="stylesheet" href="{{ $style.RelPermalink }}">\n{{ end }}'

               # netlify cms widget
               widget_str = '<script type="text/javascript" src="{{ $.Site.Params.plugins.my_scripts.netlify_widget_url }}"></script>'
               aos_str = '<link rel="stylesheet" href="{{ $.Site.Params.plugins.my_scripts.aos_css }}">'
               animate_str = '<link rel="stylesheet" href="{{ $.Site.Params.plugins.my_scripts.animate_css }}">'
               content = content.replace('</head>', '{}\n{}\n{}\n{}\n</head>'.format(scss_parser_str, widget_str, aos_str, animate_str))
               
            if p["name"] == "footer.html":
               footer_scripts_check = True
               redirecter_str = '<script type="text/javascript" src="{{ $.Site.Params.plugins.my_scripts.netlify_redirecter_url }}"></script>'
               mailer_str = '<script type="text/javascript" src="{{ $.Site.Params.plugins.my_scripts.mailer_script_url }}"></script>'
               aos_str = '<script type="text/javascript" src="{{ $.Site.Params.plugins.my_scripts.aos_js }}"></script>'
               content = content + "\n{}\n{}\n".format(redirecter_str, mailer_str, aos_str)

            with open(path, 'w') as f:
               f.write(content)
               f.close()

            replacement = '{}{{{{- partial "{}" $ -}}}}'.format(p["ind"], p["name"])
            file.replaced = file.replaced.replace(p[0], replacement)
            
         rex = rexs["data"]["nest"]
         root = re.search(rex, file.replaced, re.S)

         # if root is "homepage" key
         if root["nest_name"] == "homepage":
            home_content = self.clean_indent(root["nest_contents"])
            index_file_content = '{{ define "main" }}\n' + home_content +'\n{{ end }}'
            with open(website_folder + "layouts/index.html", 'w') as f:
               f.write(index_file_content)
               f.close()

            replacement = root["ind"] + '{{ block "main" $ }}{{ end }}'
            file.replaced = file.replaced.replace(root[0], replacement)

            with open(website_folder + "layouts/_default/baseof.html", 'w') as f:
               f.write(file.replaced)
               f.close()

         else: # if root key is not homepage, is a normal page
            page_content = self.clean_indent(root["nest_contents"])
            name = root["nest_name"]
            with open(website_folder + "layouts/partials/pages/"+name+".html", 'w') as f:
               f.write(page_content)
               f.close()

            # create the content file for this to work
            with open(website_folder + "content/"+name+".md", 'w') as f:
               f.write("")
               f.close()

         #TODO Update config file

         base_config_path = website_folder + "base_config.yml"
         if os.path.isfile(website_folder + "config.yml"):
            base_config_path = website_folder + "config.yml"

         site_config_path = website_folder + "config.yml"
         pre_site_config = Path(base_config_path).read_text()
         # site_config = yaml.load(Path(base_config_path).read_text(), yaml.FullLoader)
         new_site_config = ymlify(database["config"])

         new_site_config = hiyapyco.load([pre_site_config, new_site_config], method=hiyapyco.METHOD_MERGE)
         # new_site_config = dict_fmerge(site_config, database["config"])
         # new_site_config_yml = ymlify(new_site_config)
         new_site_config_yml = hiyapyco.dump(new_site_config, default_flow_style=None)

         # write
         with open(site_config_path, 'w') as f:
            f.write(new_site_config_yml)
            f.close()

         # data files
         for key in database["data"]:
            sections = database["data"][key]
            data_path = website_folder + "data/" + key
            Path(data_path).mkdir(parents=True, exist_ok=True)
            for s in sections:
               data_yml = ymlify(sections[s])
               with open(data_path + "/" + s + ".yml", 'w') as f:
                  f.write(data_yml)
                  f.close()

         # Data to admin config file
         admin_config = yaml.load(Path(admin_config_path).read_text(), yaml.FullLoader)

         if "collections" not in admin_config: admin_config["collections"] = [] 
         for f in cms_fields["data"]:
            admin_config["collections"].append(f)

         collection = {
            "name": "settings",
            "label": "Settings",
            "editor": {"preview": False},
            "files": [{
               "file": "config.yml",
               "label": "General",
               "name": "general",
               "fields": [
                  {"label": "baseURL", "name": "baseURL", "widget": "hidden"},
                  {"label": "languageCode", "name": "languageCode", "widget": "hidden"},
                  {"label": "assetDir", "name": "assetDir", "widget": "hidden"}
               ]
            }]
         }

         for f in cms_fields["config"]:
            if f["name"] == "params" or f["name"] == "title":
               if f["name"] == "params":
                  plugins_found = False
                  for p in f["fields"]:
                     if p["name"] == "plugins":
                        plugins_found = True
                        p["widget"] = "hidden"
                        del p["fields"]

                  if plugins_found == False:
                     f["fields"].append({"label": "plugins", "name": "plugins", "widget": "hidden"})
               collection["files"][0]["fields"].append(f)
            else:
               f["widget"] = "hidden"
               if "fields" in f:
                  del f["fields"]
               collection["files"][0]["fields"].append(f)

         admin_config["collections"].append(collection)
               
         with open(admin_config_path, 'w') as f:
            f.write(ymlify(admin_config))
            f.close()

         # clean databases for next iteration
         for t in ["config", "data"]:
            database[t] = {}
            cms_fields[t] = []

      if not head_scripts_check: print("WARNING: head required scripts not added - no head.html partial found.")
      if not footer_scripts_check: print("WARNING: footer required scripts not added - no footer.html partial found.")

   def clean_indent(self, content):
      extra_tabs = re.search(r'^(?P<extratabs>[\s]*)(?=[\S])', content)
      if extra_tabs:
         tabs = extra_tabs["extratabs"]
         content = re.sub(r'^{}'.format(tabs), r'', content, flags = re.M)
      return content

   def clean_file(self, file):
      # remove comments
      file.replaced = re.sub(r'(\n[\t ]*<!--.*?-->[\t ]*\n)', r'\n', file.replaced)
      # fix multiple breaklines before {{ end }}s
      file.replaced = re.sub(r'[\n\s\t\r]+(\n\s+?){{ end }}', r'\1{{ end }}', file.replaced)
      # multiple break lines in general
      file.replaced = re.sub(r'\n{2,}', r'\n', file.replaced)
      return file
         
   def write(self, file, dest = "__test.html"):
      with open(dest, 'w') as f:
         f.write(file.replaced)
         f.close()

config = { 
   "template_folder": "_template/",

   # vvv these are relative to $template_folder
   "static_assets": [

   ],
   "files_to_process": [
      
   ]
}

Parser(config)
print("Done :)")