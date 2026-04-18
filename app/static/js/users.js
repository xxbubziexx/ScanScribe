// Check if user is authenticated
const token = localStorage.getItem('access_token');
const username = localStorage.getItem('username');

if (!token) {
    window.location.href = '/login';
}

// Display current user
document.getElementById('currentUser').textContent = username || 'User';

// Logout handler
document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    window.location.href = '/login';
});

// Fetch with auth
async function fetchWithAuth(url, options = {}) {
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };
    
    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
    }
    
    return response;
}

// Show status message
function showStatus(message, type = 'success') {
    const statusEl = document.getElementById('statusMessage');
    statusEl.textContent = message;
    statusEl.style.display = 'block';
    
    if (type === 'success') {
        statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
        statusEl.style.border = '1px solid rgba(16, 185, 129, 0.3)';
        statusEl.style.color = 'rgb(16, 185, 129)';
    } else if (type === 'error') {
        statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
        statusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
        statusEl.style.color = 'rgb(239, 68, 68)';
    }
    
    setTimeout(() => {
        statusEl.style.display = 'none';
    }, 5000);
}

// Load users
async function loadUsers() {
    try {
        const response = await fetchWithAuth('/api/users/list');
        const users = await response.json();
        
        if (!response.ok) {
            showStatus(users.detail || 'Failed to load users', 'error');
            return;
        }
        
        document.getElementById('userCount').textContent = `${users.length} user${users.length !== 1 ? 's' : ''}`;
        
        const tbody = document.getElementById('usersTableBody');
        tbody.innerHTML = '';
        
        users.forEach(user => {
            const row = document.createElement('tr');
            row.style.borderBottom = '1px solid rgba(255, 255, 255, 0.05)';
            
            // Username
            const usernameCell = document.createElement('td');
            usernameCell.style.padding = '0.75rem';
            usernameCell.textContent = user.username;
            if (user.username === username) {
                usernameCell.innerHTML += ' <span style="color: var(--accent-primary); font-size: 0.75rem;">(You)</span>';
            }
            row.appendChild(usernameCell);
            
            // Email
            const emailCell = document.createElement('td');
            emailCell.style.padding = '0.75rem';
            emailCell.textContent = user.email;
            row.appendChild(emailCell);
            
            // Status
            const statusCell = document.createElement('td');
            statusCell.style.padding = '0.75rem';
            const statusBadge = document.createElement('span');
            statusBadge.style.padding = '0.25rem 0.5rem';
            statusBadge.style.borderRadius = '4px';
            statusBadge.style.fontSize = '0.75rem';
            if (user.is_active) {
                statusBadge.textContent = 'Active';
                statusBadge.style.background = 'rgba(16, 185, 129, 0.2)';
                statusBadge.style.color = 'rgb(16, 185, 129)';
            } else {
                statusBadge.textContent = 'Inactive';
                statusBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                statusBadge.style.color = 'rgb(239, 68, 68)';
            }
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);
            
            // Role
            const roleCell = document.createElement('td');
            roleCell.style.padding = '0.75rem';
            const roleBadge = document.createElement('span');
            roleBadge.style.padding = '0.25rem 0.5rem';
            roleBadge.style.borderRadius = '4px';
            roleBadge.style.fontSize = '0.75rem';
            if (user.is_admin) {
                roleBadge.textContent = 'Admin';
                roleBadge.style.background = 'rgba(61, 155, 214, 0.2)';
                roleBadge.style.color = 'rgb(61, 155, 214)';
            } else {
                roleBadge.textContent = 'User';
                roleBadge.style.background = 'rgba(255, 255, 255, 0.1)';
                roleBadge.style.color = 'var(--grey-text-muted)';
            }
            roleCell.appendChild(roleBadge);
            row.appendChild(roleCell);
            
            // Created date
            const createdCell = document.createElement('td');
            createdCell.style.padding = '0.75rem';
            createdCell.style.color = 'var(--grey-text-muted)';
            createdCell.style.fontSize = '0.875rem';
            const date = new Date(user.created_at);
            createdCell.textContent = date.toLocaleDateString();
            row.appendChild(createdCell);
            
            // Actions
            const actionsCell = document.createElement('td');
            actionsCell.style.padding = '0.75rem';
            actionsCell.style.textAlign = 'right';
            actionsCell.style.display = 'flex';
            actionsCell.style.gap = '0.5rem';
            actionsCell.style.justifyContent = 'flex-end';
            
            // Admin toggle button
            if (user.username !== username) {
                const adminBtn = document.createElement('button');
                adminBtn.className = 'btn btn-ghost';
                adminBtn.style.padding = '0.25rem 0.5rem';
                adminBtn.style.fontSize = '0.75rem';
                adminBtn.textContent = user.is_admin ? '👤 Demote' : '⭐ Promote';
                adminBtn.onclick = () => toggleAdmin(user.id, user.is_admin, user.username);
                actionsCell.appendChild(adminBtn);
            }
            
            // Active toggle button
            if (user.username !== username) {
                const activeBtn = document.createElement('button');
                activeBtn.className = 'btn btn-ghost';
                activeBtn.style.padding = '0.25rem 0.5rem';
                activeBtn.style.fontSize = '0.75rem';
                activeBtn.textContent = user.is_active ? '🚫 Deactivate' : '✅ Activate';
                activeBtn.onclick = () => toggleActive(user.id, user.username);
                actionsCell.appendChild(activeBtn);
            }
            
            // Delete button
            if (user.username !== username) {
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn btn-danger';
                deleteBtn.style.padding = '0.25rem 0.5rem';
                deleteBtn.style.fontSize = '0.75rem';
                deleteBtn.textContent = '🗑️ Delete';
                deleteBtn.onclick = () => deleteUser(user.id, user.username);
                actionsCell.appendChild(deleteBtn);
            }
            
            row.appendChild(actionsCell);
            tbody.appendChild(row);
        });
        
    } catch (error) {
        console.error('Failed to load users:', error);
        showStatus('Failed to load users', 'error');
    }
}

// Toggle admin status
async function toggleAdmin(userId, isCurrentlyAdmin, username) {
    const action = isCurrentlyAdmin ? 'demote' : 'promote';
    const endpoint = `/api/users/${userId}/${action}`;
    
    if (!confirm(`${isCurrentlyAdmin ? 'Demote' : 'Promote'} ${username} ${isCurrentlyAdmin ? 'from' : 'to'} admin?`)) {
        return;
    }
    
    try {
        const response = await fetchWithAuth(endpoint, { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            showStatus(data.message, 'success');
            await loadUsers();
        } else {
            showStatus(data.detail || 'Action failed', 'error');
        }
    } catch (error) {
        console.error('Failed to toggle admin:', error);
        showStatus('Action failed', 'error');
    }
}

// Toggle active status
async function toggleActive(userId, username) {
    try {
        const response = await fetchWithAuth(`/api/users/${userId}/toggle-active`, { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            showStatus(data.message, 'success');
            await loadUsers();
        } else {
            showStatus(data.detail || 'Action failed', 'error');
        }
    } catch (error) {
        console.error('Failed to toggle active:', error);
        showStatus('Action failed', 'error');
    }
}

// Delete user
async function deleteUser(userId, username) {
    if (!confirm(`⚠️ Delete user "${username}"?\n\nThis action cannot be undone.`)) {
        return;
    }
    
    if (!confirm(`Are you absolutely sure you want to delete "${username}"?`)) {
        return;
    }
    
    try {
        const response = await fetchWithAuth(`/api/users/${userId}`, { method: 'DELETE' });
        const data = await response.json();
        
        if (response.ok) {
            showStatus(data.message, 'success');
            await loadUsers();
        } else {
            showStatus(data.detail || 'Delete failed', 'error');
        }
    } catch (error) {
        console.error('Failed to delete user:', error);
        showStatus('Delete failed', 'error');
    }
}

// Load users on page load
loadUsers();
