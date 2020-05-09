import os.path

import pytest
import respx

from py_balancer_manager import BalancerManagerError


_dir = os.path.dirname(os.path.abspath(__file__))


@pytest.mark.asyncio
async def test_mocked_balancer_manager(mocked_balancer_manager):
    # cluster3 object should have 10 routes
    assert len(mocked_balancer_manager.cluster('cluster3').routes) == 10
    # cluster4 object should exist
    mocked_balancer_manager.cluster('cluster4')

    # update balancer-manager with mock-2
    await pytest.helpers.update_mocked_balancer_manager(mocked_balancer_manager, 'balancer-manager-mock-2.html')

    # cluster object should now be gone
    with pytest.raises(BalancerManagerError) as excinfo:
        mocked_balancer_manager.cluster('cluster4')
    assert 'could not locate cluster name in list of clusters: cluster4' in str(excinfo.value)

    # routes route35, route37, and route39 should be removed
    # confirm the number of routes
    assert len(mocked_balancer_manager.cluster('cluster3').routes) == 7
