// Protect the King - 2D.
// Reusable Paper2D top-down character base.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Combat/PTKCombatTarget.h"
#include "Core/PTKTypes.h"
#include "PTKTopDownCharacter.generated.h"

class UCameraComponent;
class UInputAction;
class UPTKHealthComponent;
class UInputMappingContext;
class UPaperFlipbook;
class UPaperFlipbookComponent;
class USpringArmComponent;
struct FInputActionValue;

/**
 * APTKTopDownCharacter
 * ====================
 * The single reusable movement + directional-animation implementation for
 * every 2D character in Protect the King. Ravager, King, Aegis, Wraith,
 * Reaver, Sentinel and all enemy types derive from this and supply only
 * assets and tuning values - never a second copy of this logic.
 *
 *
 * WORLD CONVENTION (read this before touching anything)
 * -----------------------------------------------------
 * Protect the King is a genuine 2D game. The three-quarter look lives
 * entirely in the artwork, exactly like Stardew Valley or 2D Zelda - it is
 * NOT produced by tilting a 3D camera over 3D geometry.
 *
 *   Play plane      : world XZ
 *   Screen right    : -X
 *   Screen up       : +Z
 *   Depth axis      : Y   (constrained to the plane; smaller Y = nearer camera)
 *   Camera          : sits at -Y and looks toward +Y (boom yaw +90)
 *
 * The camera side is not a preference, it is the only side that renders.
 * Paper2D sprites in this project are visible from -Y and invisible from +Y;
 * moving the camera to +Y makes every character disappear. That was measured,
 * not deduced - see the comment block in PTKTopDownCharacter.cpp before
 * changing CameraBoomYaw.
 *
 * Viewing the XZ plane from -Y means world +X runs LEFT across the screen, so
 * the sprite would render mirrored. That is cancelled on the sprite component
 * with a negative X scale, not by moving the camera. Movement never assumes
 * which world axis is screen-right; it asks the camera rig (UpdateMovementBasis).
 *
 * The sprite is never rotated - direction is purely a flipbook swap.
 *
 * Movement uses MOVE_Flying with GravityScale 0 and a plane constraint on Y.
 * There is no gravity and no floor in a top-down 2D game; walking is free
 * movement across the XZ plane, which is exactly what the design calls for
 * (the hero is not restricted to roads).
 *
 * See Docs/SPRITE_SPEC.md for the matching art-side contract.
 *
 * NOTE ON THE BASE CLASS: this derives from ACharacter and creates its own
 * UPaperFlipbookComponent rather than deriving from APaperCharacter.
 * APaperCharacter is declared UCLASS(MinimalAPI), so its constructor is not
 * exported from the Paper2D module and cannot be reliably linked against
 * from a game module. Owning the sprite component directly is both safe and
 * more flexible for a shared base class.
 */
UCLASS(Abstract, Blueprintable)
class PROTECTTHEKING2D_API APTKTopDownCharacter : public ACharacter, public IPTKCombatTarget
{
	GENERATED_BODY()

public:
	// --- IPTKCombatTarget ------------------------------------------
	virtual UPTKHealthComponent* GetCombatHealth() const override;
	virtual EPTKTeam GetCombatTeam() const override { return Team; }
	virtual bool IsCombatDead() const override { return IsDead(); }

public:
	APTKTopDownCharacter(const FObjectInitializer& ObjectInitializer);

	//~ Begin AActor / APawn interface
	virtual void Tick(float DeltaSeconds) override;
	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void NotifyControllerChanged() override;
	//~ End AActor / APawn interface

	/** The Paper2D visual. Named to mirror the APaperCharacter accessor. */
	UFUNCTION(BlueprintPure, Category = "PTK|Components")
	UPaperFlipbookComponent* GetSprite() const { return Sprite; }

	UFUNCTION(BlueprintPure, Category = "PTK|Components")
	UCameraComponent* GetTopDownCamera() const { return TopDownCamera; }

	UFUNCTION(BlueprintPure, Category = "PTK|Components")
	USpringArmComponent* GetCameraBoom() const { return CameraBoom; }

	/** Direction the character is currently facing. Survives stopping. */
	UFUNCTION(BlueprintPure, Category = "PTK|State")
	EPTKFacingDirection GetFacingDirection() const { return FacingDirection; }

	/** Idle, Walk or Attack. */
	UFUNCTION(BlueprintPure, Category = "PTK|State")
	EPTKMovementState GetMovementState() const { return MovementState; }

	/** True while an attack animation is playing. */
	UFUNCTION(BlueprintPure, Category = "PTK|State")
	bool IsAttacking() const { return MovementState == EPTKMovementState::Attack; }

	/**
	 * Begins an attack in the current facing direction.
	 *
	 * Exposed as a Blueprint-callable entry point (rather than living inside the
	 * input handler) so AI and scripted sequences can attack through exactly the
	 * same path as the player.
	 *
	 * Ignored if an attack is already playing, or if this character has no
	 * attack flipbook for its current facing. Returns true if one started.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Combat")
	bool StartAttack();

	UFUNCTION(BlueprintPure, Category = "PTK|Health")
	UPTKHealthComponent* GetHealthComponent() const { return HealthComponent; }

	/** True once health has hit zero and HandleDeath has run. */
	UFUNCTION(BlueprintPure, Category = "PTK|Health")
	bool IsDead() const { return MovementState == EPTKMovementState::Dead; }

	/** Which side this character fights for. Melee only hits the other one. */
	UFUNCTION(BlueprintPure, Category = "PTK|Combat")
	EPTKTeam GetTeam() const { return Team; }

	UFUNCTION(BlueprintPure, Category = "PTK|Combat")
	bool IsHostileTo(const AActor* Other) const;

	/**
	 * Whether this swing is allowed to damage Victim.
	 *
	 * Hostility is the baseline. Subclasses narrow it: an enemy swinging at
	 * one target must not damage everything else standing in the arc, which is
	 * how a blow aimed at the player ends up landing on a bystander.
	 */
	virtual bool IsValidAttackVictim(const AActor* Victim) const;

	/** Centre of the melee test for the current facing, in world space. */
	UFUNCTION(BlueprintPure, Category = "PTK|Combat")
	FVector GetAttackHitCentre() const;

	/** How far this character's attack reaches, in world units. */
	UFUNCTION(BlueprintPure, Category = "PTK|Combat")
	float GetAttackReach() const { return AttackRangeTiles * TileSize; }

	UFUNCTION(BlueprintPure, Category = "PTK|Combat")
	float GetAttackHitRadius() const { return GetAttackReach() * AttackHitWidthFactor; }

	/**
	 * Distance from the character to the centre of the melee sphere, chosen so
	 * the sphere's FAR edge lands exactly on GetAttackReach(). That keeps the
	 * sphere in front of the character instead of straddling it.
	 */
	UFUNCTION(BlueprintPure, Category = "PTK|Combat")
	float GetAttackHitDistance() const { return GetAttackReach() - GetAttackHitRadius(); }

	/** Latest movement input, already clamped so its magnitude never exceeds 1. */
	UFUNCTION(BlueprintPure, Category = "PTK|State")
	FVector2D GetMoveInput() const { return MoveInput; }

	/**
	 * Drives movement from a 2D vector. X = screen right, Y = screen up.
	 * Exposed so AI, scripted sequences and future networked input can reuse
	 * the exact same movement path as the player without duplicating it.
	 */
	UFUNCTION(BlueprintCallable, Category = "PTK|Movement")
	void SetMoveInput(FVector2D NewInput);

	/** Forces a facing direction (spawn orientation, cutscenes, ...). */
	UFUNCTION(BlueprintCallable, Category = "PTK|State")
	void SetFacingDirection(EPTKFacingDirection NewDirection);

protected:
	/**
	 * Chooses the flipbook for a state + direction pair.
	 * Virtual so later phases (Attack, Hit, Death) extend the mapping here
	 * instead of rewriting the animation update.
	 */
	UFUNCTION(BlueprintNativeEvent, Category = "PTK|Animation")
	UPaperFlipbook* SelectFlipbook(EPTKMovementState State, EPTKFacingDirection Direction) const;
	virtual UPaperFlipbook* SelectFlipbook_Implementation(EPTKMovementState State, EPTKFacingDirection Direction) const;

	/** Enhanced Input handlers. */
	void Input_Move(const FInputActionValue& Value);
	void Input_MoveCompleted(const FInputActionValue& Value);
	void Input_Attack(const FInputActionValue& Value);

	/**
	 * Counts the current attack down and releases the state when it finishes.
	 * Returns true while the attack still owns the character.
	 */
	bool TickAttack(float DeltaSeconds);

	/**
	 * Runs the melee overlap and damages every hostile inside it.
	 *
	 * Called once per swing, at the impact frame - never per tick, and never on
	 * the key press. Overridden behaviour belongs in Blueprint via OnAttackHit.
	 */
	void PerformAttackHit();

	/** Stops the character, disables collision and enters the Dead state. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Health")
	virtual void HandleDeath(AActor* Killer);

	/** Bound to the health component in BeginPlay. */
	UFUNCTION()
	void HandleHealthChanged(UPTKHealthComponent* Component, float NewHealth,
		float Delta, AActor* DamageInstigator);

	UFUNCTION()
	void HandleDeathEvent(UPTKHealthComponent* Component, AActor* Killer);

	/** Fired after a swing connects, once per victim. Prototype hook for VFX. */
	UFUNCTION(BlueprintImplementableEvent, Category = "PTK|Combat")
	void OnAttackHit(AActor* Victim, float DamageDealt);

	/** Pushes IdleFlipbooks / WalkFlipbooks onto the sprite component. */
	void UpdateAnimation();

	/** Applies capsule sizing and sprite placement. Safe to call repeatedly. */
	void ApplyCollisionAndSpriteSettings();

	/** Registers DefaultMappingContext with the local Enhanced Input subsystem. */
	void AddDefaultMappingContext();

	/**
	 * Offsets the sprite along the depth axis so characters lower on screen
	 * draw in front of characters higher on screen.
	 */
	void UpdateDepthSorting();

	/** Logs missing flipbook slots once at BeginPlay. */
	void ValidateFlipbookConfiguration() const;

	/**
	 * Recomputes the screen-space movement basis from the camera rig.
	 *
	 * Movement must never assume which world axis is "screen right" - it has to
	 * ask the camera. See the .cpp for why that axis is NOT +X in this project.
	 */
	void UpdateMovementBasis();

	// ------------------------------------------------------------------
	// Components
	// ------------------------------------------------------------------

	/** Paper2D flipbook renderer. Never rotated - direction = flipbook swap. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Components")
	TObjectPtr<UPaperFlipbookComponent> Sprite;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Components")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Components")
	TObjectPtr<UCameraComponent> TopDownCamera;

	/** The one health implementation, shared with every other character. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "PTK|Components")
	TObjectPtr<UPTKHealthComponent> HealthComponent;

	// ------------------------------------------------------------------
	// Input
	// ------------------------------------------------------------------

	/** IMC_PTK_Default. Assign in the character Blueprint. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	TObjectPtr<UInputMappingContext> DefaultMappingContext;

	/** IA_Move - must be an Axis2D (Vector2D) action. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	TObjectPtr<UInputAction> MoveAction;

	/** IA_Attack - a digital (bool) action. Leave unset for characters that cannot attack. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	TObjectPtr<UInputAction> AttackAction;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Input")
	int32 MappingContextPriority = 0;

	// ------------------------------------------------------------------
	// Movement tuning
	// ------------------------------------------------------------------

	/** Top speed in Unreal units per second. At 1 uu = 1 pixel this is px/sec. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Movement", meta = (ClampMin = "0.0"))
	float MaxMoveSpeed = 260.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Movement", meta = (ClampMin = "0.0"))
	float MoveAcceleration = 4000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Movement", meta = (ClampMin = "0.0"))
	float MoveDeceleration = 4000.0f;

	/** Input magnitudes at or below this count as no input. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Movement", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float MoveDeadZone = 0.1f;

	// ------------------------------------------------------------------
	// Facing
	// ------------------------------------------------------------------

	/** Facing used before the character has ever moved. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Facing")
	EPTKFacingDirection DefaultFacingDirection = EPTKFacingDirection::Down;

	/**
	 * 0 = exact spec rule (|X| > |Y| -> Left/Right, otherwise Up/Down).
	 * Raise slightly (0.05 - 0.15) only if an analog stick held near 45
	 * degrees flickers between the horizontal and vertical animation sets.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Facing", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float FacingHysteresis = 0.0f;

	// ------------------------------------------------------------------
	// Collision footprint
	// ------------------------------------------------------------------

	/**
	 * Gameplay footprint only - the body/feet blob.
	 * It must NOT enclose the axe, cape, glow or armour spikes, otherwise
	 * the character collides with walls from far away.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Collision", meta = (ClampMin = "1.0"))
	float CollisionRadius = 14.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Collision", meta = (ClampMin = "1.0"))
	float CollisionHalfHeight = 14.0f;

	// ------------------------------------------------------------------
	// Sprite / animation
	// ------------------------------------------------------------------

	/** Idle set - one flipbook per direction (a single frame each is fine). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	FPTKDirectionalFlipbooks IdleFlipbooks;

	/** Walk set - one flipbook per direction (8 frames each at 10 FPS). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	FPTKDirectionalFlipbooks WalkFlipbooks;

	/**
	 * Attack set - one flipbook per direction (8 frames each at 12 FPS).
	 * Leave empty for characters that never attack; StartAttack() then
	 * refuses rather than freezing them in a state with nothing to play.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	FPTKDirectionalFlipbooks AttackFlipbooks;

	/**
	 * Death collapse - a single non-directional flipbook.
	 *
	 * Death is not directional: a character falls the same way whichever way it
	 * was facing, and the delivered art is one 8-frame sequence rather than
	 * four. Left empty, the character simply freezes on its last living frame.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	TObjectPtr<UPaperFlipbook> DeathFlipbook;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation", meta = (ClampMin = "0.01"))
	float DeathPlayRate = 1.0f;

	/**
	 * Sprite position relative to the capsule centre.
	 * The default of zero is correct when the sprite pivot is the feet
	 * anchor and the capsule is the feet blob - actor origin, capsule centre
	 * and feet contact point then all coincide, which is what keeps the
	 * character from bouncing when animations change.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	FVector SpriteRelativeLocation = FVector::ZeroVector;

	/** Playback rate multipliers on top of the authored FPS of each flipbook. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation", meta = (ClampMin = "0.0"))
	float IdlePlayRate = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation", meta = (ClampMin = "0.0"))
	float WalkPlayRate = 1.0f;

	/**
	 * Multiplier on the attack flipbook's authored FPS.
	 *
	 * Playback rate and movement speed are deliberately independent: making the
	 * swing read better must never change how fast Ravager walks, and vice
	 * versa. The attack's duration is derived from the flipbook length divided
	 * by this rate, so raising it shortens the state to match what is on screen.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation", meta = (ClampMin = "0.01"))
	float AttackPlayRate = 1.0f;

	/**
	 * Carries the walk cycle phase across a direction change so turning
	 * while walking does not snap the legs back to frame 1.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	bool bPreserveWalkCyclePhase = true;

	/** Keeps the sprite world rotation fixed regardless of actor rotation. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Animation")
	bool bLockSpriteWorldRotation = true;

	// ------------------------------------------------------------------
	// Combat
	//
	// ANIMATION ONLY. There is deliberately no damage, health, hitbox,
	// knockback, cooldown or combo here yet. When damage does arrive, the
	// impact frame is Attack_*_05 - the fifth of the eight frames, where the
	// axe is at the bottom of its swing.
	// ------------------------------------------------------------------

	/**
	 * Holds the facing captured at the start of the attack until it finishes,
	 * so a swing cannot rotate mid-animation and show two directions at once.
	 * Movement is still allowed; only the facing is pinned.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat")
	bool bLockFacingDuringAttack = true;

	/**
	 * Lets a new attack interrupt one that is already playing.
	 * Off for the prototype: the brief says the animation must be allowed to
	 * finish, and mashing the key should not restart the swing every frame.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat")
	bool bAllowAttackInterrupt = false;

	/**
	 * Fallback duration used only if the attack flipbook reports no length.
	 * Never hit with valid assets; it exists so a broken import degrades into
	 * a brief animation rather than locking the character in Attack forever.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat", meta = (ClampMin = "0.01"))
	float AttackFallbackDuration = 0.667f;

	/** Side this character fights for. Guards and enemies override in their tier. */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "PTK|Combat")
	EPTKTeam Team = EPTKTeam::Guards;

	/** Damage one connecting swing deals. Prototype: Ravager 25, Swarm Node 15. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat", meta = (ClampMin = "0.0"))
	float AttackDamage = 25.0f;

	/**
	 * How far along the attack animation the hit lands, as a fraction of its
	 * length. Both characters use an 8-frame attack whose strongest pose is
	 * frame 5, and frame 5 begins at 4/8 - hence 0.5.
	 *
	 * Damage is tied to the animation rather than to the key press, so a swing
	 * that is interrupted before this point never connects.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AttackImpactFraction = 0.5f;

	/**
	 * World units per map tile. One project-wide number, so reach can be stated
	 * in tiles instead of scattering raw world units through the code.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat", meta = (ClampMin = "1.0"))
	float TileSize = 64.0f;

	/**
	 * How far the attack reaches, in TILES. This is the single number that
	 * defines a character's threat range - the AI's stop distance and the melee
	 * sphere are both derived from it, so they can never disagree.
	 *
	 * Guards deliberately out-range enemies: a guard must be able to strike
	 * before the thing closing on it can strike back. See APTKGuardCharacter
	 * and APTKEnemyCharacter for the two tiers' values.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat", meta = (ClampMin = "0.1"))
	float AttackRangeTiles = 1.0f;

	/**
	 * Lateral half-width of the swing, as a fraction of its reach.
	 *
	 * The melee test is a sphere placed in front of the character, NOT the
	 * sprite bounds: Ravager's axe and cape reach far outside his body and must
	 * never act as a permanent weapon hitbox. This factor sets how wide that
	 * sphere is, and therefore how many enemies one swing can catch.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat", meta = (ClampMin = "0.1", ClampMax = "0.9"))
	float AttackHitWidthFactor = 0.45f;

	/** Draws the melee sphere for one second on every swing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Debug")
	bool bDrawAttackHit = false;

	/**
	 * True: one swing may damage every valid victim in the arc.
	 * False: it stops at the first, so a single blow injures a single body.
	 *
	 * Guards sweep a crowd; that is the point of a big axe. Enemies do not -
	 * see APTKEnemyCharacter, which turns this off.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Combat")
	bool bAttackHitsMultipleTargets = true;

	/** Seconds the corpse remains before the actor is destroyed. 0 keeps it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Health", meta = (ClampMin = "0.0"))
	float DestroyDelayAfterDeath = 2.0f;

	// ------------------------------------------------------------------
	// Depth sorting
	// ------------------------------------------------------------------

	/** Lower on screen draws in front. Safe to leave on for every character. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Rendering")
	bool bEnableDepthSorting = true;

	/** Depth offset per unit of height. Keep small; it only breaks ties. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Rendering", meta = (ClampMin = "0.0"))
	float DepthSortScale = 0.1f;

	// ------------------------------------------------------------------
	// Camera rig
	// ------------------------------------------------------------------

	/** Turn off for AI characters that never own the view. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Camera")
	bool bEnableCameraRig = true;

	/**
	 * Orthographic width in Unreal units. At 1 uu = 1 pixel this is exactly
	 * how many source pixels are visible across the screen, so integer ratios
	 * against the output resolution stay pixel-crisp: 960 is a clean 2x on a
	 * 1920-wide viewport.
	 *
	 * Sized against the real artwork. Ravager measures 117 px from helmet to
	 * boots, so at 16:9 this puts him at roughly 22% of screen height - normal
	 * for a top-down action game. The previous 480 was chosen before the art
	 * existed and would have filled 43% of the screen with one character.
	 *
	 * Revisit once the real map exists; it should be tuned against tile scale.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Camera", meta = (ClampMin = "1.0"))
	float CameraOrthoWidth = 960.0f;

	/** Distance the camera sits back along -Y. Affects clipping, not zoom. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Camera", meta = (ClampMin = "1.0"))
	float CameraDistance = 1000.0f;

	/**
	 * Smooth follow. Note: lag puts the camera on non-integer pixel
	 * positions, which can shimmer on high-contrast pixel art. Set
	 * bUseCameraLag to false for a locked, perfectly crisp camera.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Camera")
	bool bUseCameraLag = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Camera", meta = (ClampMin = "0.0"))
	float CameraLagSpeed = 12.0f;

	// ------------------------------------------------------------------
	// Debug
	// ------------------------------------------------------------------

	/** Prints facing + state on screen. Prototype aid only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Debug")
	bool bShowDebugState = false;

	// ------------------------------------------------------------------
	// Runtime state
	// ------------------------------------------------------------------

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	EPTKFacingDirection FacingDirection = EPTKFacingDirection::Down;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	EPTKMovementState MovementState = EPTKMovementState::Idle;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	FVector2D MoveInput = FVector2D::ZeroVector;

	/**
	 * World direction that appears as "right" on screen, derived from the camera.
	 * UpdateMovementBasis() recomputes this from the actual camera rig so it can
	 * never drift out of sync with the view.
	 */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	FVector MovementRightVector = FVector(1.0f, 0.0f, 0.0f);

	/** World direction that appears as "up" on screen. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	FVector MovementUpVector = FVector(0.0f, 0.0f, 1.0f);

	/** World direction the camera looks along. Used to bias depth sorting. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	FVector MovementDepthVector = FVector(0.0f, -1.0f, 0.0f);

	/** Seconds left on the current attack. Zero when not attacking. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	float AttackTimeRemaining = 0.0f;

	/** Facing captured when the attack began; held while bLockFacingDuringAttack. */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|State")
	EPTKFacingDirection AttackFacingDirection = EPTKFacingDirection::Down;

	/**
	 * Victims already damaged by the CURRENT swing.
	 *
	 * This is what makes one swing deal one hit. Without it the impact test
	 * would fire on every tick it stayed true, and a single axe swing would
	 * damage the same enemy several times over.
	 */
	UPROPERTY()
	TSet<TObjectPtr<AActor>> AttackHitActors;

	/** True once the current swing has run its impact test. */
	bool bAttackImpactApplied = false;

	/** Total length of the current attack, for locating the impact moment. */
	float AttackDuration = 0.0f;

	/** Previous frame state - used to decide whether the walk phase can carry over. */
	EPTKMovementState PreviousMovementState = EPTKMovementState::Idle;

	/** Last play rate pushed to the sprite, so we only call SetPlayRate on change. */
	float AppliedPlayRate = -1.0f;

	/** Ensures the one-shot startup diagnostic dump only runs on the first tick. */
	bool bLoggedStartupDiagnostics = false;

	/**
	 * Dumps sprite, camera and view-target state once, on the first tick.
	 *
	 * Runs on the first tick rather than BeginPlay because possession and view
	 * target selection are not settled until after BeginPlay. Gated on
	 * bShowDebugState.
	 */
	void LogStartupDiagnostics();
};
