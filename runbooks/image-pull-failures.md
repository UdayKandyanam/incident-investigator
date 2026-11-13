# Image pull failures

## Symptoms

Pods sit in ImagePullBackOff or ErrImagePull and never start. The container
has zero restarts because it never ran. Events for the pod show a Failed
message from the kubelet naming the image it could not pull.

## Checks

Read the full error in the pod event. A manifest unknown or not found error
means the tag does not exist in the registry, which is usually a typo in the
tag or a build that never pushed. A 401 or 403 means the registry rejected
the credentials. A timeout usually means the node cannot reach the registry
at all.

Compare the image string in the pod spec with the tag the build actually
pushed. Check that the imagePullSecret named on the service account exists
in the same namespace as the pod.

## Fix

Correct the image tag in the deployment, or refresh the pull secret when the
registry credentials have rotated. Roll the deployment and watch one pod
come up before closing the incident. For a service like the sample checkout-api
api, confirm the new pod passes its readiness probe and is serving traffic.

## Prevention

Fail the pipeline when the pushed tag does not match the tag written into
the deployment manifest. Alert on ImagePullBackOff lasting more than five
minutes so a bad tag is caught during the rollout, not by a customer.
