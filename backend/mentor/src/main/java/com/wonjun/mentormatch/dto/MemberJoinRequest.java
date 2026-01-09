package com.wonjun.mentormatch.dto;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.Role;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
public class MemberJoinRequest {
    private String email;
    private String name;
    private String password;
    private Role role; // "MENTOR" 또는 "MENTEE"

    // DTO -> Entity 변환 메서드 (편의상 여기에 만듭니다)
    public Member toEntity() {
        return new Member(email, name, password, role);
    }
}