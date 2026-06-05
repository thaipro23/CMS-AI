# v25.9.14.5.1 – create_child return normalization hotfix

## Reported failure

`store.create_child(...)` created a `library_content` child but returned a plain usage-key string. The connector then passed that string into `store.update_item`, producing:

```text
'str' object has no attribute 'block_type'
```

## Fix

The connector now normalizes all known `create_child` return shapes (XBlock descriptor, opaque UsageKey, or string usage key), resolves the real draft XBlock, and only then updates fields. It also refreshes the parent before reuse checks after a partial create failure.

## Honest scope

This fixes the return-type/update failure. It does not prove that Ulmo.3 accepts direct `library_content` selected-component assignment. After deployment, retry insertion and inspect the next connector response plus Studio state.
