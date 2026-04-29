from random import shuffle
import hashlib

namespaces = []

for i in range(10):
    namespaces.append(f"namespace{i}")

shuffle(namespaces)

pod_names = ["pod6", "pod2", "pod5"]

result = {}
for pod_name in pod_names:
    assigned_namespaces = []
    for namespace in namespaces:
        hash_index = int(
                        hashlib.sha256(
                            namespace.encode("utf-8")
                        ).hexdigest(),
                        16,
                    ) % len(pod_names)
        if pod_names[hash_index] == pod_name:
            assigned_namespaces.append(namespace)
    result[pod_name] = assigned_namespaces

print(result)