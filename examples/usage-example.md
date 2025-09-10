# Usage example

This example shows how to create a DB based on a GitHub repository (in this case [skorch](https://github.com/skorch-dev/skorch)) and run queries against it.

## Prepare

```sh
mkdir /tmp/skorch
cd /tmp/skorch
git clone --depth 1 --branch v1.2.0 https://github.com/skorch-dev/skorch.git
cd skorch
kieker create skorch/ --exclude skorch/tests -o result.sqlite -v -j4
```

## Queries

### Find function `to_numpy`

```sh
sqlite3 -header -column -quote result.sqlite 'SELECT file, start_line, end_line, def_text
FROM functions
WHERE qualified_name like "%to_numpy";'
```

```
'file','start_line','end_line','def_text'

'/tmp/skorch/utils.py',127,164,'
def to_numpy(X):
    """Generic function to convert a pytorch tensor to numpy.

    This function tries to unpack the tensor(s) from supported
    data structures (e.g., dicts, lists, etc.) but doesn''t go
    beyond.

    Returns X when it already is a numpy array.

    """
    if isinstance(X, np.ndarray):
        return X

    if isinstance(X, Mapping):
        return {key: to_numpy(val) for key, val in X.items()}

    if is_pandas_ndframe(X):
        return X.values

    if isinstance(X, (tuple, list)):
        return type(X)(to_numpy(x) for x in X)

    if _is_slicedataset(X):
        return np.asarray(X)

    if not is_torch_data_type(X):
        raise TypeError("Cannot convert this data type to a numpy array.")

    if X.is_cuda:
        X = X.cpu()

    if hasattr(X, ''is_mps'') and X.is_mps:
        X = X.cpu()

    if X.requires_grad:
        X = X.detach()

    return X.numpy()
'
```

### Find function locations calling `np.asarray`

```sh
sqlite3 -header -column result.sqlite "SELECT f.file, f.start_line, f.end_line, f.qualified_name
FROM calls c
JOIN functions f ON f.id = c.caller_id
WHERE c.callee_repr = 'np.asarray'
ORDER BY f.file, f.start_line;"
```

```
file                       start_line  end_line  qualified_name                                    
-------------------------  ----------  --------  --------------------------------------------------
/tmp/skorch/classifier.py  98          118       classifier.NeuralNetClassifier.classes_           
/tmp/skorch/helper.py      262         268       helper.SliceDataset.__array__                     
/tmp/skorch/helper.py      262         268       helper.SliceDataset.__array__                     
/tmp/skorch/hf.py          46          64        hf._HuggingfaceTokenizerBase.get_feature_names_out
/tmp/skorch/hf.py          126         148       hf._HuggingfaceTokenizerBase.inverse_transform    
/tmp/skorch/hf.py          150         183       hf._HuggingfaceTokenizerBase.tokenize             
/tmp/skorch/utils.py       127         164       utils.to_numpy 
```

### Find long functions without a docstring

```sh
sqlite3 -header -column result.sqlite "SELECT f.qualified_name, fm.lines_of_code
FROM functions f
JOIN function_metrics fm ON fm.function_id = f.id
WHERE fm.lines_of_code > 50
  AND (f.docstring IS NULL OR f.docstring = '')
ORDER BY fm.lines_of_code DESC;"
```

```
qualified_name               lines_of_code
---------------------------  -------------
history.History.__getitem__  60           
net.NeuralNet.__init__       52           
_version._cmpkey             51 
```

### Show the ten modules with the highest amount of functions

```sh
sqlite3 -header -column result.sqlite "SELECT m.module, COUNT(f.id) AS function_count
FROM modules m
JOIN functions f ON f.module_id = m.id
GROUP BY m.module
ORDER BY function_count DESC
LIMIT 10;"
```

```
module                    function_count
------------------------  --------------
net                       92
callbacks.logging         58
_version                  48
hf                        47
utils                     45            
callbacks.training        42            
llm.classifier            38            
history                   32            
probabilistic             29            
callbacks.scoring         25            
```

### List the location and name of all classes that inherit from class `NeuralNet`

```sh
sqlite3 -header -column result.sqlite "SELECT c.name AS subclass_name,
  c.file,
  c.start_line,
  c.end_line,
  c.qualified_name
FROM classes c
JOIN inheritance i ON i.subclass_id = c.id
WHERE i.superclass_name = 'NeuralNet'
ORDER BY c.file, c.start_line;"
```

```
subclass_name              file                          start_line  end_line  qualified_name                      
-------------------------  ----------------------------  ----------  --------  ------------------------------------
NeuralNetClassifier        /tmp/skorch/classifier.py     57          235       classifier.NeuralNetClassifier      
NeuralNetBinaryClassifier  /tmp/skorch/classifier.py     266         386       classifier.NeuralNetBinaryClassifier
GPBase                     /tmp/skorch/probabilistic.py  34          392       probabilistic.GPBase                
NeuralNetRegressor         /tmp/skorch/regressor.py      39          85        regressor.NeuralNetRegressor 
```

### Find functions with highest number of parameters

```sh
sqlite3 -header -column result.sqlite "WITH param_counts AS (
  SELECT p.function_id, COUNT(*) AS nparams
  FROM parameters p
  GROUP BY p.function_id
)
SELECT f.qualified_name, nparams
FROM param_counts pc
JOIN functions f ON f.id = pc.function_id
WHERE pc.nparams >= 8
ORDER BY nparams DESC, f.qualified_name
LIMIT 10;"
```

```
qualified_name                                  nparams
----------------------------------------------  -------
net.NeuralNet.__init__                          21     
hf.HuggingfaceTokenizer.__init__                16     
callbacks.training.Checkpoint.__init__          15     
llm.classifier.FewShotClassifier.__init__       13     
callbacks.training.TrainEndCheckpoint.__init__  12     
_doctor.SkorchDoctor.plot_activations           11     
_doctor.SkorchDoctor.plot_gradients             11     
callbacks.logging.MlflowLogger.__init__         11     
hf.HuggingfacePretrainedTokenizer.__init__      11     
llm.classifier.ZeroShotClassifier.__init__      11
```

### Find all classes and functions using the `contextmanager` decorator

```sh
sqlite3 -header -column result.sqlite "SELECT (CASE d.target_kind WHEN 'class' THEN 'class' ELSE 'function' END) AS kind,
       (CASE d.target_kind
          WHEN 'class'    THEN (SELECT qualified_name FROM classes  WHERE id = d.target_id)
          ELSE                 (SELECT qualified_name FROM functions WHERE id = d.target_id)
        END) AS target_qname, d.file  
FROM decorators d
WHERE d.name_repr = 'contextmanager'
ORDER BY kind, target_qname;"
```

```
kind      target_qname                               file                            
--------  -----------------------------------------  --------------------------------
function  callbacks.scoring._cache_net_forward_iter  /tmp/skorch/callbacks/scoring.py
function  net.NeuralNet._current_init_context        /tmp/skorch/net.py              
function  utils.open_file_like                       /tmp/skorch/utils.py 
```

### Find all modules that import the `tabulate` package

```sh
sqlite3 -header -column result.sqlite "SELECT m.module, i.imported, i.file, i.start_line
FROM imports i
JOIN modules m ON m.id = i.module_id
WHERE i.imported LIKE 'tabulate.%'             
ORDER BY m.module, i.file, i.start_line;"
```

```
module             imported           file                              start_line
-----------------  -----------------  --------------------------------  ----------
callbacks.logging  tabulate.tabulate  /tmp/skorch/callbacks/logging.py  13
```

### Find methods modifying reading the `module_` attribute on `NeuralNet` or assigning to it

```sh
sqlite3 -header -column result.sqlite "SELECT f.qualified_name, a.op_kind, f.file, f.start_line
FROM attributes a
JOIN classes c ON a.class_id = c.id
JOIN functions f ON a.function_id = f.id
WHERE c.qualified_name = 'net.NeuralNet' AND a.attribute = 'module_' AND a.op_kind IN ('read', 'assign','augassign');"
```

```
qualified_name                   op_kind  file                              start_line
-------------------------------  -------  --------------------------------  ----------
net.NeuralNet.initialize_module  assign   /tmp/skorch/skorch/skorch/net.py  618       
net.NeuralNet.infer              read     /tmp/skorch/skorch/skorch/net.py  1536      
net.NeuralNet.infer              read     /tmp/skorch/skorch/skorch/net.py  1536 
```
